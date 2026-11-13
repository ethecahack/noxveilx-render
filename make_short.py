#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_short.py  —  عامل تركيب فيديوهات NoxveilX (يعمل على جهازك)

الوضع الأساسي (مع n8n):
    python make_short.py --n8n
  لكل صيغة في config.json (short ثم long) يسحب السيناريو الجاهز من n8n،
  يركّب الفيديو (صوت edge-tts + صور Pollinations + كابشن + حركة)،
  وللفيديو الطويل: فصول دقيقة في الوصف + صورة مصغّرة، ثم يرسله لـ n8n ليرفعه ليوتيوب.

وضع الاختبار (بدون رفع):
    python make_short.py --n8n --no-upload
  يركّب فقط ويحفظ الفيديو في مجلد output حتى تشاهده قبل التشغيل الحقيقي.
  (السيناريو يعود تلقائيًا للطابور بعد 3 ساعات)
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import studio
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ------------------------- الإعدادات -------------------------

VOICES = {"en": os.environ.get("VOICE_EN", "en-US-ChristopherNeural"), "ar": "ar-SA-HamedNeural"}
FONT = os.environ.get("CAPTION_FONT", "Arial")

FORMATS = {
    # w, h, fps, tts rate, caption size, caption margin, words per caption, upload cap MB, zoom scale
    "short": dict(w=1080, h=1920, fps=30, rate="+6%", cap_size=84, cap_margin=420,
                  cap_words=3, max_mb=14.0, zscale=2.0, crf=26, maxrate="1200k"),
    "long": dict(w=1920, h=1080, fps=25, rate="+0%", cap_size=62, cap_margin=70,
                 cap_words=5, max_mb=80.0, zscale=1.5, crf=26, maxrate="1100k"),
}
THUMB_W, THUMB_H = 1280, 720
HTTP_TIMEOUT = 180


def load_config():
    cfg_path = HERE / "config.json"
    if not cfg_path.exists() and os.environ.get("NOXVEIL_TOKEN"):
        # وضع السحابة (GitHub Actions): الإعدادات من متغيرات البيئة
        return {
            "n8n_base_url": os.environ.get("N8N_BASE_URL", "https://farizk16.app.n8n.cloud"),
            "token": os.environ["NOXVEIL_TOKEN"].strip(),
            "langs": [x for x in os.environ.get("LANGS", "en").split(",") if x],
            "formats": [x for x in os.environ.get("FORMATS", "short,long").split(",") if x],
        }
    if not cfg_path.exists():
        die(f"ملف الإعدادات غير موجود: {cfg_path}")
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa
        die(f"ملف config.json غير صالح: {e}")


# ------------------------- أدوات مساعدة -------------------------

LOG_FILE = None


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    if LOG_FILE:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa
            pass


def die(msg, code=1):
    log(f"[خطأ] {msg}")
    sys.exit(code)


class StepError(Exception):
    pass


def run(cmd, cwd=None):
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "")[-1500:]
        raise StepError(f"فشل الأمر {Path(str(cmd[0])).name}:\n{tail}")
    return res


def check_tools():
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([tool, "-version"], capture_output=True)
        except FileNotFoundError:
            die(f"'{tool}' غير مثبّت. شغّل install.bat أولًا (يثبّت ffmpeg).")
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        die("مكتبة edge-tts غير مثبّتة. شغّل install.bat أولًا.")
    try:
        import requests  # noqa: F401
    except ImportError:
        die("مكتبة requests غير مثبّتة. شغّل install.bat أولًا.")


def ffprobe_duration(path):
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        raise StepError(f"تعذّر قراءة مدة الملف: {path}")


def bold_font_path():
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if Path(p).exists():
            return p
    return None


# ------------------------- الصوت (edge-tts) -------------------------

def tts(text, lang, rate, workdir, name):
    """يولّد name.mp3 و name.vtt لمقطع نصي واحد."""
    (workdir / f"{name}.txt").write_text(text, encoding="utf-8")
    for attempt in range(1, 4):
        try:
            run([sys.executable, "-m", "edge_tts", "--voice", VOICES[lang], f"--rate={rate}",
                 "--file", f"{name}.txt",
                 "--write-media", f"{name}.mp3", "--write-subtitles", f"{name}.vtt"],
                cwd=workdir)
            audio = workdir / f"{name}.mp3"
            if audio.exists() and audio.stat().st_size > 1000:
                return audio, workdir / f"{name}.vtt"
        except StepError as e:
            log(f"الصوت ({name}): محاولة {attempt} فشلت")
            if attempt == 3:
                raise e
        time.sleep(5 * attempt)
    raise StepError("لم يُنتج edge-tts ملف صوت صالح.")


# ------------------------- الصور (Pollinations) -------------------------

def fetch_image(prompt, dst, w, h):
    prompt = prompt[:330] + ", single cinematic frame, one scene, no split screen, no collage, no text"
    base_q = urllib.parse.quote(prompt)
    for attempt in range(1, 6):
        seed = (int(time.time()) + attempt * 131) % 1000000
        url = (f"https://image.pollinations.ai/prompt/{base_q}"
               f"?width={w}&height={h}&nologo=true&private=true&referrer=noxveilx&model=flux&seed={seed}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                data = r.read()
            if len(data) < 5000:
                raise ValueError("صورة غير صالحة")
            dst.write_bytes(data)
            return dst
        except Exception as e:  # noqa
            log(f"صورة {dst.name}: محاولة {attempt} فشلت ({e})")
            time.sleep(6 * attempt)
    raise StepError(f"تعذّر جلب الصورة {dst.name}.")


# ------------------------- الكابشن (.ass) -------------------------

def parse_vtt(path):
    def ts(t):
        t = t.replace(",", ".")
        parts = t.split(":")
        if len(parts) == 2:
            parts = ["0"] + parts
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)

    words, block = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "-->" in line:
            a, b = line.split("-->")
            block = [ts(a.strip().split()[0]), ts(b.strip().split()[0]), ""]
        elif line.strip() == "":
            if block and block[2].strip():
                words.append((block[0], block[1], block[2].strip()))
            block = []
        elif block:
            block[2] = (block[2] + " " + line.strip()).strip()
    if block and len(block) == 3 and block[2].strip():
        words.append((block[0], block[1], block[2].strip()))
    return words


def ass_time(sec):
    cs = int(round(max(sec, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def split_to_words(cues):
    """يحوّل أي توقيت (كلمات أو جُمل كاملة) إلى توقيت لكل كلمة بالتناسب."""
    out = []
    for start, end, text in cues:
        toks = text.split()
        if len(toks) <= 1:
            out.append((start, end, text))
            continue
        total = sum(len(t) + 1 for t in toks)
        dur = max(end - start, 0.05 * len(toks))
        t = start
        for tok in toks:
            d = dur * (len(tok) + 1) / total
            out.append((t, t + d, tok))
            t += d
    return out


def build_ass(words, fmt, out_path):
    f = FORMATS[fmt]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= f["cap_words"] or w[2].endswith((".", "?", "!")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    def esc(t):
        return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")

    lines = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {f['w']}
PlayResY: {f['h']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},{f['cap_size']},&H00FFFFFF,&H00000000,&H64000000,-1,0,1,6,2,2,120,120,{f['cap_margin']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""]
    for ch in chunks:
        start, end = ch[0][0], ch[-1][1]
        if end <= start:
            end = start + 0.6
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,"
                     + esc(" ".join(w[2] for w in ch)))
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ------------------------- التجميع (ffmpeg) -------------------------

def build_scene(img, dur, idx, workdir, fmt):
    f = FORMATS[fmt]
    w, h, fps, zs = f["w"], f["h"], f["fps"], f["zscale"]
    frames = max(2, int(round(dur * fps)))
    sw, sh = int(w * zs) // 2 * 2, int(h * zs) // 2 * 2
    # تنويع الحركة: مشهد يقترب ومشهد يبتعد
    if idx % 2 == 1:
        z = f"min(1+0.12*on/{frames},1.12)"
    else:
        z = f"max(1.12-0.12*on/{frames},1.0)"
    # قص أسفل الصورة 8% لإزالة أي علامة مائية من مولّد الصور
    vf = (f"crop=iw:ih*0.92:0:0,scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")
    out = f"scene_{idx:03d}.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-i", img.name, "-t", f"{dur:.3f}",
         "-r", str(fps), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", out], cwd=workdir)
    return workdir / out


def assemble(scene_clips, audio_dur, workdir, music_file, fmt):
    f = FORMATS[fmt]
    (workdir / "scenes.txt").write_text(
        "".join(f"file '{c.name}'\n" for c in scene_clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "scenes.txt",
         "-c", "copy", "video_silent.mp4"], cwd=workdir)

    inputs = ["-i", "video_silent.mp4", "-i", "audio.wav"]
    if music_file and Path(music_file).exists():
        inputs += ["-stream_loop", "-1", "-i", str(Path(music_file).resolve())]
        vol = "0.10" if fmt == "short" else "0.07"
        fc = (f"[0:v]ass=captions.ass[v];[2:a]volume={vol}[bg];"
              "[1:a][bg]amix=inputs=2:duration=first:dropout_transition=0,dynaudnorm[a]")
    else:
        fc = "[0:v]ass=captions.ass[v];[1:a]dynaudnorm[a]"

    maxrate_k = int(f["maxrate"].rstrip("k"))
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc,
         "-map", "[v]", "-map", "[a]", "-t", f"{audio_dur + 0.3:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", str(f["crf"]),
         "-maxrate", f["maxrate"], "-bufsize", f"{maxrate_k * 2}k", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "final.mp4"],
        cwd=workdir)

    final = workdir / "final.mp4"
    size_mb = final.stat().st_size / (1024 * 1024)
    if size_mb > f["max_mb"]:
        kbps = int((f["max_mb"] * 0.9 * 8 * 1024) / max(audio_dur, 1) - 128)
        kbps = max(kbps, 400)
        log(f"الحجم {size_mb:.1f}MB كبير، إعادة ضغط على {kbps}k ...")
        run(["ffmpeg", "-y", "-i", "final.mp4", "-c:v", "libx264", "-preset", "veryfast",
             "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
             "-c:a", "copy", "-movflags", "+faststart", "final_small.mp4"], cwd=workdir)
        (workdir / "final_small.mp4").replace(final)
    return final


def make_thumbnail(prompt, text, workdir):
    """صورة مصغّرة 1280x720: صورة سينمائية + تظليل يسار + نص عريض كبير."""
    base = workdir / "thumb_base.jpg"
    fetch_image(prompt + ", ultra detailed, high contrast, vivid colors, dramatic", base, THUMB_W, THUMB_H)
    words = (text or "").upper().split()
    if len(words) > 2:
        mid = len(words) // 2
        text_lines = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
    else:
        text_lines = " ".join(words)
    vf = (f"crop=iw:ih*0.92:0:0,scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,crop={THUMB_W}:{THUMB_H},"
          "eq=contrast=1.12:saturation=1.25,"
          "drawbox=x=0:y=0:w=iw*0.62:h=ih:color=black@0.45:t=fill")
    font = bold_font_path()
    if text_lines.strip() and font:
        (workdir / "thumb_text.txt").write_text(text_lines, encoding="utf-8")
        # نسخ الخط لمجلد العمل لتفادي مشاكل مسارات ويندوز داخل فلاتر ffmpeg
        (workdir / "thumb_font.ttf").write_bytes(Path(font).read_bytes())
        vf += (",drawtext=fontfile=thumb_font.ttf:textfile=thumb_text.txt:fontsize=118:"
               "fontcolor=0xFFD400:borderw=9:bordercolor=black:line_spacing=10:"
               "x=60:y=(h-text_h)/2")
    run(["ffmpeg", "-y", "-i", base.name, "-vf", vf, "-q:v", "3", "thumbnail.jpg"], cwd=workdir)
    return workdir / "thumbnail.jpg"


def fmt_ts(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_sections(script, fmt):
    raw = script["scenes"]
    data = json.loads(raw) if isinstance(raw, str) else raw
    if fmt == "long":
        if not isinstance(data, dict) or not data.get("sections"):
            raise StepError("سيناريو الفيديو الطويل بلا فصول.")
        sections = [s for s in data["sections"] if s.get("narration") and s.get("scenes")]
        if len(sections) < 3:
            raise StepError("الفيديو الطويل يحتاج 3 فصول على الأقل.")
        return sections, data.get("thumbnail_prompt", ""), data.get("thumbnail_text", "")
    scenes = [s for s in (data if isinstance(data, list) else []) if s.get("image_prompt")][:10]
    if len(scenes) < 3:
        raise StepError("السيناريو يحتوي مشاهد أقل من 3.")
    return [{"heading": "", "narration": script["narration"], "scenes": scenes}], "", ""


def render(script, workdir, music_file):
    fmt = script.get("format", "short")
    f = FORMATS[fmt]
    lang = script["lang"]
    portrait = fmt == "short"
    T = 0.4  # transition length
    sections, thumb_prompt, thumb_text = get_sections(script, fmt)

    # 1) voice per section -> exact timings for chapters, captions and shots
    log(f"Voice-over ({len(sections)} part(s)) ...")
    offsets, durs, all_words, wavs = [], [], [], []
    t = 0.0
    for i, sec in enumerate(sections, 1):
        audio, subs = tts(sec["narration"], lang, f["rate"], workdir, f"part_{i:02d}")
        wav = f"part_{i:02d}.wav"
        gap = 0.45 if (fmt == "long" and i < len(sections)) else 0.0
        af = f"apad=pad_dur={gap}" if gap else "anull"
        run(["ffmpeg", "-y", "-i", audio.name, "-af", af, "-ar", "44100", "-ac", "2",
             "-c:a", "pcm_s16le", wav], cwd=workdir)
        d = ffprobe_duration(workdir / wav)
        offsets.append(t)
        durs.append(d)
        all_words += [(a + t, b + t, w) for a, b, w in split_to_words(parse_vtt(subs))]
        wavs.append(wav)
        t += d
    audio_dur = t
    (workdir / "audio_list.txt").write_text("".join(f"file '{w}'\n" for w in wavs), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "audio_list.txt",
         "-c:a", "pcm_s16le", "audio.wav"], cwd=workdir)
    log(f"Audio length: {audio_dur:.1f}s")

    # 2) shot plan
    plan, section_starts = [], set()
    for i, sec in enumerate(sections):
        n = len(sec["scenes"])
        if i > 0:
            section_starts.add(len(plan))
        for sc in sec["scenes"]:
            plan.append((sc, durs[i] / n))
    base = [d for _, d in plan]

    # 3) real footage (AI image only as fallback)
    log(f"Collecting footage for {len(plan)} shots ...")
    used, shots, n_video = set(), [], 0
    for i, (sc, d) in enumerate(plan, 1):
        length = d + (T if i < len(plan) else 0.5)
        try:
            kind, src = studio.get_visual(sc, f, portrait, length, used, workdir, i)
        except Exception as e:  # noqa
            raise StepError(f"shot {i}: {e}")
        n_video += kind == "video"
        shots.append(studio.build_shot(kind, src, length, i, workdir, f))
        if i % 5 == 0:
            log(f"  ... {i}/{len(plan)} shots ({n_video} real clips)")
    log(f"Shots ready: {n_video} real video clips, {len(plan) - n_video} AI images")

    # 4) edit: transitions, captions, sound design
    log("Editing (transitions, captions, sound) ...")
    video, cuts = studio.join_with_transitions(shots, base, workdir, f, section_starts, T)
    hook = script.get("title", "") if fmt == "short" else ""
    chapters = [(o, s.get("heading", "")) for o, s in zip(offsets, sections)][1:] if fmt == "long" else []
    font = os.environ.get("CAPTION_FONT", FONT)
    studio.build_captions(all_words, fmt, f, workdir / "captions.ass", font, hook, chapters)
    sfx = studio.build_sfx(audio_dur, cuts, workdir / "sfx.wav", seed=int(script.get("id", 1)))
    music = music_file if music_file and Path(music_file).exists() else studio.pick_music(HERE, audio_dur, workdir)
    final = studio.final_mix(video, workdir / "audio.wav", music, sfx, workdir / "captions.ass",
                             audio_dur, workdir, f)
    size_mb = final.stat().st_size / (1024 * 1024)
    if size_mb > f["max_mb"]:
        kbps = max(int((f["max_mb"] * 0.9 * 8 * 1024) / max(audio_dur, 1) - 160), 400)
        log(f"{size_mb:.1f}MB is large, re-encoding at {kbps}k ...")
        run(["ffmpeg", "-y", "-i", "final.mp4", "-c:v", "libx264", "-preset", "veryfast",
             "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
             "-c:a", "copy", "-movflags", "+faststart", "final_small.mp4"], cwd=workdir)
        (workdir / "final_small.mp4").replace(final)
    log(f"Video ready: {final} ({final.stat().st_size / 1048576:.1f}MB)")

    desc = script.get("description", "")
    desc = desc.replace("Visuals are AI-generated illustrations. Facts checked against public sources.",
                        "Footage: licensed stock clips and AI-generated illustrations. Facts checked against public sources.")
    extra = {"thumbnail": None, "description": desc}
    if fmt == "long":
        chapters_txt = "\n".join(f"{fmt_ts(o)} {s.get('heading') or 'Part ' + str(i + 1)}"
                                  for i, (o, s) in enumerate(zip(offsets, sections)))
        extra["description"] = desc.strip() + "\n\nChapters:\n" + chapters_txt
        (workdir / "chapters.txt").write_text(chapters_txt, encoding="utf-8")
        log("Chapters:\n" + chapters_txt)
        try:
            log("Thumbnail ...")
            first_q = (plan[0][0].get("stock_query") or "") if plan else ""
            extra["thumbnail"] = studio.make_thumbnail(thumb_prompt or plan[0][0].get("image_prompt", ""),
                                                       thumb_text, first_q, workdir,
                                                       os.environ.get("THUMB_FONT") or bold_font_path())
            log(f"Thumbnail ready: {extra['thumbnail']}")
        except Exception as e:  # noqa
            log(f"Thumbnail failed (publishing without it): {e}")
    return final, extra


def cleanup(workdir):
    keep = ("final.mp4", "script.json", "thumbnail.jpg", "chapters.txt")  # noqa
    for p in workdir.iterdir():
        if p.name not in keep:
            try:
                p.unlink()
            except Exception:  # noqa
                pass


# ------------------------- الاتصال بـ n8n -------------------------

def fetch_next(cfg, lang, fmt):
    import requests
    url = cfg["n8n_base_url"].rstrip("/") + "/webhook/noxveil-next"
    r = requests.get(url, params={"lang": lang, "format": fmt, "token": cfg["token"]}, timeout=90)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise StepError(f"n8n رد بخطأ {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not data.get("id") or not data.get("narration"):
        raise StepError(f"رد n8n ناقص: {str(data)[:300]}")
    return data


def upload(cfg, script, video_path, extra):
    import requests
    url = cfg["n8n_base_url"].rstrip("/") + "/webhook/noxveil-upload"
    fields = {
        "id": str(script["id"]), "lang": script["lang"], "format": script.get("format", "short"),
        "title": script["title"], "description": extra.get("description", ""),
        "tags": script.get("tags", ""), "token": cfg["token"],
    }
    last = None
    for attempt in range(1, 3):
        handles = []
        try:
            fh = open(video_path, "rb")
            handles.append(fh)
            files = [("video", ("video.mp4", fh, "video/mp4"))]
            thumb = extra.get("thumbnail")
            if thumb and Path(thumb).exists():
                th = open(thumb, "rb")
                handles.append(th)
                files.append(("thumb", ("thumbnail.jpg", th, "image/jpeg")))
            r = requests.post(url, data=fields, files=files, timeout=1800)
            if r.status_code == 200:
                return r.json() if r.text else {"ok": True}
            last = StepError(f"n8n رد بخطأ {r.status_code}: {r.text[:300]}")
            if r.status_code in (400, 401, 503):
                break
        except Exception as e:  # noqa
            last = e
        finally:
            for h in handles:
                h.close()
        log(f"الرفع: محاولة {attempt} فشلت")
        time.sleep(20)
    raise StepError(f"فشل الرفع: {last}")


def run_worker(no_upload):
    cfg = load_config()
    for key in ("n8n_base_url", "token", "langs"):
        if not cfg.get(key):
            die(f"الحقل '{key}' ناقص في config.json")
    formats = cfg.get("formats") or ["short", "long"]
    outroot = HERE / "output"
    music = cfg.get("music_file") or str(HERE / "assets" / "music.mp3")
    failures = 0
    for lang in cfg["langs"]:
        if lang not in VOICES:
            log(f"تخطّي لغة غير مدعومة: {lang}")
            continue
        for fmt in formats:
            if fmt not in FORMATS:
                log(f"تخطّي صيغة غير معروفة: {fmt}")
                continue
            try:
                log(f"===== {lang} / {fmt} =====")
                script = fetch_next(cfg, lang, fmt)
                if not script:
                    log("لا يوجد سيناريو جاهز لهذه الصيغة الآن.")
                    continue
                script["lang"] = lang
                script["format"] = fmt
                log(f"السيناريو #{script['id']}: {script['title']}")
                workdir = outroot / fmt / f"{script['id']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                workdir.mkdir(parents=True, exist_ok=True)
                (workdir / "script.json").write_text(
                    json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
                final, extra = render(script, workdir, music)
                if no_upload:
                    log("وضع الاختبار: لم يتم الرفع. شاهد الفيديو من المسار أعلاه.")
                    try:
                        os.startfile(str(workdir))  # يفتح المجلد في ويندوز
                    except Exception:  # noqa
                        pass
                    continue
                log("الرفع إلى يوتيوب عبر n8n ...")
                res = upload(cfg, script, final, extra)
                log(f"تم النشر بنجاح ✅ {res}")
                cleanup(workdir)
            except Exception as e:  # noqa
                failures += 1
                log(f"[خطأ] {lang}/{fmt}: {e}")
    if failures:
        sys.exit(1)


def main():
    global LOG_FILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--n8n", action="store_true", help="سحب السيناريو من n8n والتركيب والرفع")
    ap.add_argument("--no-upload", action="store_true", help="تركيب فقط بدون رفع (للاختبار)")
    args = ap.parse_args()

    (HERE / "logs").mkdir(exist_ok=True)
    LOG_FILE = HERE / "logs" / "worker.log"
    studio.set_logger(log)
    check_tools()
    if not args.n8n:
        die("شغّل السكربت مع --n8n (أو استخدم run_daily.bat / test_render.bat)")
    run_worker(args.no_upload or os.environ.get("DRY_RUN") == "1")


if __name__ == "__main__":
    main()
