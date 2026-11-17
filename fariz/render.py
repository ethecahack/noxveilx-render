#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FARIZ KANAAN — محرك الإنتاج.
يأخذ ملف محتوى JSON (منشور ثابت / كاروسيل / تفاعلي / ريل) ويُخرج ملفات جاهزة للنشر:
  out/POST_XXX/slide_01.jpg ...   (1080×1080)
  out/POST_XXX/cover.jpg + reel.mp4 (1080×1920)
  out/POST_XXX/meta.json           (الكابشن والهاشتاقات والمصادر)

الاستخدام:
  python fariz/render.py fariz/content/POST_005.json [--out fariz/out]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402

VOICE = os.environ.get("FK_VOICE", "ar-SA-HamedNeural")
FPS = 30


def log(m):
    print(m, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-1500:]}")
    return r


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())


# ---------------- الخلفيات ----------------

def bg_for(prompt, w, h, cache: Path, seed):
    if not prompt:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"bg_{w}x{h}_{seed}.jpg"
    return D.fetch_background(prompt, w, h, out, seed=seed)


# ---------------- الصور الثابتة ----------------

def render_slides(post, R, out: Path, cache: Path):
    slides = post.get("slides", [])
    n = len(slides)
    files = []
    got = []
    for i, sl in enumerate(slides, 1):
        seed = post["post_number"] * 100 + i
        bg = bg_for(sl.get("bg"), 1080, 1080, cache, seed)
        if not bg and sl.get("bg"):
            bg = bg_for(sl["bg"].split(",")[0] + ", dark antique scene", 1080, 1080, cache, seed + 50)
        if bg:
            got.append(bg)
        elif got:
            bg = got[-1]
        idx = f"{i:02d} / {n:02d}" if n > 1 else ""
        html = D.square_slide(sl, bg, idx=idx, swipe=(n > 1 and i < n))
        f = out / f"slide_{i:02d}.jpg"
        R.shot(html, f, 1080, 1080, jpeg=True)
        files.append(f.name)
        log(f"  slide {i}/{n} -> {f.name}")
    return files


# ---------------- الريل ----------------

def tts(text, mp3: Path):
    if os.environ.get("FK_NO_NET") == "1":
        # معاينة بدون إنترنت: صمت بطول تقديري
        secs = max(2.5, len(text.split()) / 2.3)
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{secs:.2f}", "-q:a", "4", str(mp3)])
        return
    txt = mp3.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    last = ""
    for attempt in range(6):
        voice = VOICE if attempt < 4 else "ar-EG-ShakirNeural"
        r = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--rate=-4%", "--file", str(txt),
                            "--write-media", str(mp3)], capture_output=True, text=True)
        if mp3.exists() and mp3.stat().st_size > 2000:
            return
        last = (r.stderr or r.stdout)[-600:]
        log(f"  tts attempt {attempt + 1} failed ({voice}): {last}")
        import time as _t
        _t.sleep(4 + attempt * 4)
    raise RuntimeError("TTS failed: " + last[-300:])


def scene_clip(bg_img: Path, frame_png: Path, cap_png: Path, secs: float, k: int, out: Path):
    """صورة خلفية بحركة كاميرا بطيئة + طبقة العلامة + الكابشن."""
    frames = int(secs * FPS) + 1
    # تبديل اتجاه الحركة بين المشاهد
    moves = [
        "z='min(1.0+0.0009*on,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='1.18-0.0009*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='1.12':x='(iw-iw/zoom)*on/{F}':y='ih/2-(ih/zoom/2)'".replace("{F}", str(frames)),
        "z='1.12':x='(iw-iw/zoom)*(1-on/{F})':y='ih/2-(ih/zoom/2)'".replace("{F}", str(frames)),
    ]
    zp = moves[k % len(moves)]
    vf = (f"[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
          f"zoompan={zp}:d={frames}:s=1080x1920:fps={FPS},eq=saturation=0.85:contrast=1.04,"
          f"fade=t=in:st=0:d=0.35[bg];"
          f"[bg][1:v]overlay=0:0[a];[2:v]fade=t=in:st=0.15:d=0.3:alpha=1[c];[a][c]overlay=0:0,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(bg_img), "-loop", "1", "-i", str(frame_png),
         "-loop", "1", "-i", str(cap_png), "-filter_complex", vf, "-map", "[v]", "-t", f"{secs:.3f}",
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)])


def still_clip(img: Path, secs: float, out: Path):
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img),
         "-vf", f"scale=1080:1920,zoompan=z='min(1.0+0.0006*on,1.06)':d={int(secs * FPS) + 1}:s=1080x1920:fps={FPS},fade=t=in:st=0:d=0.4,format=yuv420p",
         "-t", f"{secs:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)])


def fallback_bg_jpg(R, w, h, out: Path):
    html = D.page(w, h, None, "")
    R.shot(html, out, w, h, jpeg=True)
    return out


def render_reel(post, R, out: Path, cache: Path):
    reel = post["reel"]
    n = post["post_number"]
    tmp = Path(tempfile.mkdtemp(prefix=f"fk{n}_"))
    # الغلاف
    cbg = bg_for(reel["cover"].get("bg"), 1080, 1920, cache, n * 100)
    R.shot(D.reel_cover(reel["cover"], cbg), out / "cover.jpg", 1080, 1920, jpeg=True)
    log("  cover.jpg")
    frame = tmp / "frame.png"
    R.shot(D.reel_frame(), frame, 1080, 1920, transparent=True)
    fb = None
    clips, audios = [], []
    # بطاقة افتتاحية قصيرة (الغلاف) 1.6 ث مع صمت
    c0 = tmp / "c00.mp4"
    still_clip(out / "cover.jpg", 1.6, c0)
    clips.append(c0)
    sil0 = tmp / "a00.m4a"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "1.6", "-c:a", "aac", str(sil0)])
    audios.append(sil0)
    for k, sc in enumerate(reel["scenes"], 1):
        mp3 = tmp / f"v{k:02d}.mp3"
        tts(sc["voice"], mp3)
        secs = duration(mp3) + 0.45
        bg = bg_for(sc.get("bg"), 1080, 1920, cache, n * 100 + 10 + k)
        if not bg and cbg:
            bg = cbg
        if not bg:
            fb = fb or fallback_bg_jpg(R, 1080, 1920, tmp / "fallback.jpg")
            bg = fb
        cap = tmp / f"cap{k:02d}.png"
        R.shot(D.reel_caption(sc["caption"], tuple(sc.get("gold", []))), cap, 1080, 1920, transparent=True)
        clip = tmp / f"c{k:02d}.mp4"
        scene_clip(bg, frame, cap, secs, k, clip)
        a = tmp / f"a{k:02d}.m4a"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af", f"apad=pad_dur=0.45,atrim=0:{secs:.3f}", "-ar", "24000", "-ac", "1", "-c:a", "aac", str(a)])
        clips.append(clip)
        audios.append(a)
        log(f"  scene {k}/{len(reel['scenes'])} ({secs:.1f}s)")
    # بطاقة الختام
    ebg = bg_for(reel["cover"].get("bg"), 1080, 1920, cache, n * 100)
    end_img = tmp / "end.jpg"
    R.shot(D.reel_end(reel, ebg), end_img, 1080, 1920, jpeg=True)
    ce = tmp / "c99.mp4"
    still_clip(end_img, 3.2, ce)
    clips.append(ce)
    se = tmp / "a99.m4a"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "3.2", "-c:a", "aac", str(se)])
    audios.append(se)
    # دمج
    lst = tmp / "v.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips))
    alst = tmp / "a.txt"
    alst.write_text("".join(f"file '{a}'\n" for a in audios))
    video = tmp / "video.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(video)])
    voice = tmp / "voice.m4a"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c:a", "aac", str(voice)])
    total = duration(video)
    # خلفية صوتية هادئة مولّدة بالكود (بلا حقوق): نغمتان منخفضتان مع تلاشٍ
    pad = tmp / "pad.m4a"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f=110:d={total:.2f}", "-f", "lavfi", "-i", f"sine=f=164.8:d={total:.2f}",
         "-f", "lavfi", "-i", f"anoisesrc=d={total:.2f}:c=brown:a=0.02",
         "-filter_complex", f"[0][1][2]amix=inputs=3:normalize=0,lowpass=f=900,volume=0.045,afade=t=in:d=2,afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5[p]",
         "-map", "[p]", "-ar", "44100", "-c:a", "aac", str(pad)])
    final = out / "reel.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voice), "-i", str(pad),
         "-filter_complex", "[1:a]aresample=44100,volume=1.6[v];[v][2:a]amix=inputs=2:normalize=0:duration=first[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "2500k", "-bufsize", "5000k", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", "-shortest", str(final)])
    log(f"  reel.mp4 ({duration(final):.1f}s)")
    return ["cover.jpg", "reel.mp4"]


def render_post(path: Path, out_root: Path):
    post = json.loads(path.read_text(encoding="utf-8"))
    n = int(post["post_number"])
    out = out_root / f"POST_{n:03d}"
    out.mkdir(parents=True, exist_ok=True)
    cache = out_root / "_bg_cache"
    log(f"POST {n:03d} [{post['type']}] {post['title']}")
    R = D.Renderer()
    try:
        if post["type"] == "reel":
            files = render_reel(post, R, out, cache)
        else:
            files = render_slides(post, R, out, cache)
    finally:
        R.close()
    tags = post.get("hashtags", "")
    meta = {
        "post_number": n, "type": post["type"], "title": post["title"], "lang": post.get("lang", "ar"),
        "files": files,
        "caption": (post.get("caption", "").strip() + ("\n\n" + tags if tags else "")).strip(),
        "sources": post.get("sources", []),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=str(HERE / "out"))
    a = ap.parse_args()
    for f in a.files:
        render_post(Path(f), Path(a.out))


if __name__ == "__main__":
    main()
