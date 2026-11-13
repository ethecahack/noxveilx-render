# -*- coding: utf-8 -*-
"""
studio.py - NoxveilX editing engine.

- Real stock footage per scene (Pexels, then Pixabay), AI image only as a fallback.
- No women or girls on screen: filename/slug/tag filter + Gemini vision check (when a key is set).
- Cinematic grade, slow camera moves, transitions between every shot.
- Word-by-word highlighted captions, hook title (shorts) and chapter cards (long).
- Sound design: whooshes on cuts, impact on the open, music bed ducked under the voice.
- Bold, high-contrast thumbnail built with Pillow.
"""

import base64
import io
import json
import math
import os
import random
import re
import subprocess
import time
import urllib.parse
import wave
from pathlib import Path

import numpy as np
import requests

HTTP_TIMEOUT = 60
UA = {"User-Agent": "Mozilla/5.0 (NoxveilX renderer)"}

PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash-lite")

# words that mean a clip is likely to show a woman / girl
FEMALE_WORDS = re.compile(
    r"\b(woman|women|girl|girls|female|lady|ladies|mother|mom|mum|bride|wife|daughter|sister|"
    r"her|she|model|bikini|dancer|ballerina|actress|queen|princess|grandmother|grandma|aunt|"
    r"niece|girlfriend|feminine|makeup|lipstick|pregnant|couple|family|wedding|selfie)\b",
    re.I,
)

TRANSITIONS = ["fade", "smoothleft", "smoothup", "circleopen", "dissolve", "slideleft",
               "smoothright", "radial", "fadeblack", "wipeleft"]

_log = print


def set_logger(fn):
    global _log
    _log = fn


class StudioError(Exception):
    pass


def _run(cmd, cwd=None):
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "")[-1500:]
        raise StudioError(f"{Path(str(cmd[0])).name} failed:\n{tail}")
    return res


def probe_duration(path):
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ safety check

def _img_b64(data, max_side=512):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa
        return base64.b64encode(data).decode()


_last_gemini = [0.0]
_MODELS = [m for m in [os.environ.get("GEMINI_VISION_MODEL", ""), "gemini-flash-lite-latest", "gemini-flash-latest",
                       "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"] if m]
_model_ok = [None]


def _gemini(parts):
    """Returns the model's text answer, or None if no model is reachable."""
    if not GEMINI_KEY:
        return None
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 30}}
    models = [_model_ok[0]] if _model_ok[0] else list(_MODELS)
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        for attempt in range(4):
            wait = 4.2 - (time.time() - _last_gemini[0])  # stay under the free-tier rate limit
            if wait > 0:
                time.sleep(wait)
            _last_gemini[0] = time.time()
            try:
                r = requests.post(url, json=body, timeout=40)
            except Exception:  # noqa
                time.sleep(5)
                continue
            if r.status_code == 404 or r.status_code == 400:
                break  # try the next model name
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code != 200:
                _log(f"  vision check unavailable ({r.status_code}): {r.text[:120]}")
                return None
            _model_ok[0] = model
            cand = r.json().get("candidates", [{}])[0]
            return " ".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    if not _model_ok[0]:
        _log("  vision check unavailable (no Gemini model reachable)")
    return None


def check_frames(images, query="", allow_men=False):
    """Returns (ok, reason). ok=None when the check could not run."""
    if not GEMINI_KEY or not images:
        return None, "no check"
    q = (query or "").strip()
    parts = [{"text": (
        "These are frames from ONE stock video clip. Answer three questions about ALL frames together.\n"
        "FEMALE: does any frame show a woman or a girl (face, body, partial body, clearly female silhouette, "
        "or a statue/painting/drawing of a female)?\n"
        "PEOPLE: does any frame show any person at all?\n"
        f"MATCH: does the clip clearly show '{q}'?\n"
        "Reply in exactly this format: FEMALE=YES|NO PEOPLE=YES|NO MATCH=YES|NO")}]
    for data in images[:4]:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _img_b64(data)}})
    ans = _gemini(parts)
    if ans is None:
        return None, "no check"
    a = ans.upper().replace(" ", "")
    if "FEMALE=YES" in a:
        return False, "woman visible"
    if "PEOPLE=YES" in a and not allow_men:
        return False, "people visible"
    if q and "MATCH=NO" in a:
        return False, "does not match"
    return True, "ok"


def shows_female(images):
    ok, reason = check_frames(images)
    if ok is None:
        return None
    return reason == "woman visible"


def _get_bytes(url, timeout=30):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.content


# ------------------------------------------------------------------ stock footage

def _pick_file(files, portrait, min_w):
    best, best_score = None, None
    for f in files or []:
        w, h = f.get("width") or 0, f.get("height") or 0
        if not f.get("link") or not w or not h:
            continue
        if portrait and h < w:
            continue
        if not portrait and w < h:
            continue
        short_side = min(w, h)
        if short_side < min_w:
            continue
        score = abs(short_side - (1080 if not portrait else 1080))
        if best_score is None or score < best_score:
            best, best_score = f, score
    return best


def _download(url, dst, max_mb=80):
    with requests.get(url, headers=UA, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        size = 0
        with open(dst, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if size > max_mb * 1048576:
                    raise StudioError("clip too large")
                fh.write(chunk)
    if Path(dst).stat().st_size < 50_000:
        raise StudioError("clip too small")
    return dst


def pexels_clip(query, portrait, min_dur, used, dst):
    if not PEXELS_KEY or not query:
        return None
    params = {"query": query, "per_page": 20, "size": "medium",
              "orientation": "portrait" if portrait else "landscape"}
    try:
        r = requests.get("https://api.pexels.com/videos/search", params=params,
                         headers={"Authorization": PEXELS_KEY, **UA}, timeout=30)
        if r.status_code != 200:
            _log(f"  Pexels {r.status_code}")
            return None
        videos = r.json().get("videos", [])
    except Exception as e:  # noqa
        _log(f"  Pexels error: {e}")
        return None
    random.shuffle(videos)
    videos.sort(key=lambda v: 0 if (v.get("duration") or 0) >= min_dur else 1)
    checked = 0
    for v in videos:
        if checked >= 8:
            break
        vid = f"pexels-{v.get('id')}"
        if vid in used:
            continue
        slug = (v.get("url") or "").lower().replace("-", " ")
        if FEMALE_WORDS.search(slug):
            continue
        f = _pick_file(v.get("video_files"), portrait, 720)
        if not f:
            continue
        pics = [p.get("picture") for p in (v.get("video_pictures") or []) if p.get("picture")]
        sample = [pics[i] for i in sorted({0, len(pics) // 3, 2 * len(pics) // 3, len(pics) - 1}) if pics] if pics else []
        try:
            frames = [_get_bytes(u) for u in sample[:4]]
        except Exception:  # noqa
            frames = []
        checked += 1
        ok, why = check_frames(frames, query, allow_men=bool(re.search(r"\bman\b|\bmen\b", query, re.I)))
        if ok is False:
            _log(f"  skipped a clip ({why})")
            continue
        try:
            _download(f["link"], dst)
            used.add(vid)
            return dst
        except Exception as e:  # noqa
            _log(f"  download failed: {e}")
    return None


def pixabay_clip(query, portrait, min_dur, used, dst):
    if not PIXABAY_KEY or not query:
        return None
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": PIXABAY_KEY, "q": query, "per_page": 30, "safesearch": "true"},
                         headers=UA, timeout=30)
        hits = r.json().get("hits", []) if r.status_code == 200 else []
    except Exception as e:  # noqa
        _log(f"  Pixabay error: {e}")
        return None
    random.shuffle(hits)
    for h in hits:
        vid = f"pixabay-{h.get('id')}"
        if vid in used or FEMALE_WORDS.search(h.get("tags", "")):
            continue
        vids = h.get("videos") or {}
        cand = [vids.get(k) for k in ("large", "medium") if vids.get(k)]
        cand = [c for c in cand if c.get("url") and c.get("width")]
        good = [c for c in cand if (c["height"] >= c["width"]) == portrait] or ([] if portrait else cand)
        if not good:
            continue
        pick = good[0]
        thumbs = [c.get("thumbnail") for c in cand if c.get("thumbnail")]
        try:
            frames = [_get_bytes(u) for u in thumbs[:2]]
        except Exception:  # noqa
            frames = []
        ok, why = check_frames(frames, query, allow_men=bool(re.search(r"\bman\b|\bmen\b", query, re.I)))
        if ok is False:
            _log(f"  skipped a clip ({why})")
            continue
        try:
            _download(pick["url"], dst)
            used.add(vid)
            return dst
        except Exception as e:  # noqa
            _log(f"  download failed: {e}")
    return None


_last_poll = [0.0]
POLL_GAP = float(os.environ.get("POLLINATIONS_GAP", "18"))  # anonymous tier allows ~1 request per 15s


def ai_image(prompt, dst, w, h, tries=5):
    base = (prompt or "dark cinematic mysterious landscape")[:300]
    base += ", single cinematic frame, photorealistic, no text, no watermark, no women, no girls"
    q = urllib.parse.quote(base)
    for attempt in range(1, tries + 1):
        wait = POLL_GAP - (time.time() - _last_poll[0])
        if wait > 0:
            time.sleep(wait)
        _last_poll[0] = time.time()
        seed = random.randint(1, 999999)
        url = (f"https://image.pollinations.ai/prompt/{q}?width={w}&height={h}"
               f"&nologo=true&private=true&referrer=noxveilx&model=flux&seed={seed}")
        try:
            r = requests.get(url, headers=UA, timeout=180)
            if r.status_code in (402, 429, 503):
                _log(f"  image attempt {attempt}: busy ({r.status_code}), waiting")
                time.sleep(20 * attempt)
                continue
            r.raise_for_status()
            data = r.content
            if len(data) < 5000:
                raise StudioError("bad image")
            if shows_female([data]) is True:
                _log("  regenerating image (woman visible)")
                continue
            Path(dst).write_bytes(data)
            return dst
        except Exception as e:  # noqa
            _log(f"  image attempt {attempt} failed ({e})")
            time.sleep(5 * attempt)
    raise StudioError(f"could not get an image for: {prompt[:60]}")


def get_visual(scene, fmt_cfg, portrait, dur, used, workdir, idx):
    """Returns (kind, path) where kind is 'video' or 'image'."""
    query = (scene.get("stock_query") or "").strip()
    if not query:
        cap = scene.get("caption") or ""
        query = " ".join(re.findall(r"[A-Za-z]+", cap)[:4])
    vid = workdir / f"clip_{idx:03d}.mp4"
    for fn in (pexels_clip, pixabay_clip):
        got = fn(query, portrait, dur, used, vid)
        if got:
            return "video", got
    # simpler query (first two words) before falling back to an AI image
    short_q = " ".join(query.split()[:2])
    if short_q and short_q != query:
        for fn in (pexels_clip, pixabay_clip):
            got = fn(short_q, portrait, dur, used, vid)
            if got:
                return "video", got
    img = workdir / f"img_{idx:03d}.jpg"
    ai_image(scene.get("image_prompt") or query, img, fmt_cfg["w"], fmt_cfg["h"])
    return "image", img


# ------------------------------------------------------------------ shots

GRADE = "eq=contrast=1.10:saturation=1.12:brightness=-0.02:gamma=0.97,vignette=PI/5"


def build_shot(kind, src, dur, idx, workdir, fmt_cfg):
    w, h, fps = fmt_cfg["w"], fmt_cfg["h"], fmt_cfg["fps"]
    out = workdir / f"shot_{idx:03d}.mp4"
    frames = max(2, int(round(dur * fps)))
    if kind == "video":
        clip_len = probe_duration(src) or dur
        start = 0.0
        speed = 1.0
        if clip_len >= dur + 1.5:
            start = random.uniform(0.3, min(clip_len - dur - 0.3, 6.0))
        elif clip_len < dur:
            speed = max(clip_len / dur, 0.66)  # slow down a little, then loop if still short
        sw, sh = int(w * 1.10) // 2 * 2, int(h * 1.10) // 2 * 2
        drift = random.choice(["(iw-ow)*t/{d}", "(iw-ow)*(1-t/{d})", "(iw-ow)/2"]).format(d=f"{dur:.3f}")
        vf = (f"setpts=PTS/{speed:.4f},scale={sw}:{sh}:force_original_aspect_ratio=increase,"
              f"crop={sw}:{sh},crop={w}:{h}:x='{drift}':y='(ih-oh)/2',fps={fps},{GRADE},"
              f"setsar=1,format=yuv420p")
        _run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-stream_loop", "-1", "-i", src.name,
              "-t", f"{dur:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "20", "-pix_fmt", "yuv420p", out.name], cwd=workdir)
    else:
        zs = fmt_cfg["zscale"]
        sw, sh = int(w * zs) // 2 * 2, int(h * zs) // 2 * 2
        z = (f"min(1+0.14*on/{frames},1.14)" if idx % 2 else f"max(1.14-0.14*on/{frames},1.0)")
        vf = (f"crop=iw:ih*0.92:0:0,scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps},"
              f"{GRADE},setsar=1,format=yuv420p")
        _run(["ffmpeg", "-y", "-loop", "1", "-i", src.name, "-t", f"{dur:.3f}", "-vf", vf,
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out.name],
             cwd=workdir)
    return out


def join_with_transitions(shots, base_durs, workdir, fmt_cfg, section_starts=(), T=0.4):
    """shots[i] lasts base_durs[i] + T (except the last). Returns (video path, cut times)."""
    if len(shots) == 1:
        return shots[0], []
    inputs, fc, cuts = [], [], []
    for s in shots:
        inputs += ["-i", s.name]
    prev = "[0:v]"
    t = 0.0
    for i in range(1, len(shots)):
        t += base_durs[i - 1]
        trans = "fadeblack" if i in section_starts else TRANSITIONS[(i * 7) % len(TRANSITIONS)]
        if trans == "fadeblack" and i not in section_starts:
            trans = "fade"
        label = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition={trans}:duration={T}:offset={t:.3f}{label}")
        prev = label
        cuts.append(t)
    out = workdir / "video_silent.mp4"
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", prev,
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-r", str(fmt_cfg["fps"]), out.name], cwd=workdir)
    return out, cuts


# ------------------------------------------------------------------ captions

def _ass_time(sec):
    cs = int(round(max(sec, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _wrap(text, n):
    words, lines, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) >= n:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return "\\N".join(lines)


def build_captions(words, fmt, fmt_cfg, out_path, font, hook_text="", chapters=()):
    """words: [(start, end, word)]. chapters: [(start_sec, heading)]."""
    w, h = fmt_cfg["w"], fmt_cfg["h"]
    per = 3 if fmt == "short" else 6
    size = 112 if fmt == "short" else 80
    margin_v = int(h * 0.30) if fmt == "short" else 70
    chunks, cur = [], []
    for wd in words:
        cur.append(wd)
        if len(cur) >= per or wd[2].endswith((".", "?", "!", ",")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    yellow = "&H0000D4FF"
    lines = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,{7 if fmt == 'short' else 5},3,2,90,90,{margin_v},1
Style: Hook,{font},{78 if fmt == 'short' else 70},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00101010,-1,0,0,0,100,100,1,0,3,18,0,8,70,70,{int(h * 0.12)},1
Style: Chapter,{font},{64},&H0000D4FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,5,3,7,80,80,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""]

    for ch in chunks:
        texts = [_esc(x[2]).upper() if fmt == "short" else _esc(x[2]) for x in ch]
        for k, wd in enumerate(ch):
            start = wd[0]
            end = ch[k + 1][0] if k + 1 < len(ch) else max(wd[1], start + 0.25)
            if end <= start:
                end = start + 0.2
            parts = []
            for j, t in enumerate(texts):
                if j == k:
                    pop = r"\t(0,90,\fscx118\fscy118)\t(90,180,\fscx108\fscy108)" if fmt == "short" else ""
                    parts.append(f"{{\\c{yellow}{pop}}}{t}{{\\r}}")
                else:
                    parts.append(t)
            lines.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")

    if hook_text:
        txt = _esc(hook_text.upper())
        lines.append(f"Dialogue: 2,{_ass_time(0.05)},{_ass_time(2.9)},Hook,,0,0,0,,"
                     f"{{\\fad(120,250)\\t(0,180,\\fscx106\\fscy106)\\t(180,320,\\fscx100\\fscy100)}}"
                     f"{_wrap(txt, 18 if fmt == 'short' else 34)}")
    for start, heading in chapters:
        if not heading:
            continue
        lines.append(f"Dialogue: 2,{_ass_time(start + 0.3)},{_ass_time(start + 3.3)},Chapter,,0,0,0,,"
                     f"{{\\fad(250,350)}}{_esc(heading.upper())}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------ sound design

SR = 44100


def _write_wav(path, stereo):
    stereo = np.clip(stereo, -1, 1)
    data = (stereo * 32000).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())


def _lowpass(x, k):
    k = max(int(k), 1)
    return np.convolve(x, np.ones(k) / k, mode="same")


def _whoosh(rng, length=0.7):
    n = int(SR * length)
    noise = rng.standard_normal(n)
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * t) ** 2 * np.exp(-1.5 * t)
    # sweep: blend from dark to bright noise
    dark, bright = _lowpass(noise, 40), noise - _lowpass(noise, 6)
    mix = dark * (1 - t) + bright * t * 0.6
    sig = mix * env
    return sig / (np.max(np.abs(sig)) + 1e-9)


def _impact(length=1.8):
    n = int(SR * length)
    t = np.arange(n) / SR
    freq = 70 * np.exp(-t * 1.2) + 32
    phase = 2 * np.pi * np.cumsum(freq) / SR
    sig = np.sin(phase) * np.exp(-t * 2.4)
    rng = np.random.default_rng(7)
    sig += _lowpass(rng.standard_normal(n), 25) * np.exp(-t * 9) * 0.6
    return sig / (np.max(np.abs(sig)) + 1e-9)


def build_sfx(total, cuts, out_path, seed=1):
    rng = np.random.default_rng(seed)
    n = int(SR * (total + 2))
    track = np.zeros(n)
    imp = _impact()
    track[:len(imp)] += imp * 0.9
    for c in cuts:
        w = _whoosh(rng)
        s = int(max(c - 0.35, 0) * SR)
        e = min(s + len(w), n)
        track[s:e] += w[:e - s] * 0.55
    stereo = np.stack([track, np.roll(track, 90)], axis=1)
    _write_wav(out_path, stereo * 0.9)
    return out_path


def build_music(total, out_path, seed=3):
    """Dark ambient bed synthesised locally (used when no music files are provided)."""
    rng = np.random.default_rng(seed)
    n = int(SR * (total + 2))
    t = np.arange(n) / SR
    roots = rng.choice([[55.0, 82.41, 110.0, 130.81], [49.0, 73.42, 98.0, 116.54],
                        [58.27, 87.31, 116.54, 138.59]])
    sig = np.zeros(n)
    for i, f in enumerate(roots):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.03 + 0.017 * i) * t + i)
        detune = np.sin(2 * np.pi * f * t) + 0.6 * np.sin(2 * np.pi * f * 1.003 * t)
        sig += detune * lfo / (i + 1.2)
    # slow pulse every 2 seconds like a heartbeat
    pulse_env = np.exp(-((t % 2.0) / 0.12)) * 0.5
    sig += np.sin(2 * np.pi * 45 * t) * pulse_env
    air = _lowpass(rng.standard_normal(n), 60) * 0.25 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))
    sig += air
    fade = np.minimum(1, np.minimum(t / 3.0, (t[-1] - t) / 3.0))
    sig = sig * fade
    sig /= np.max(np.abs(sig)) + 1e-9
    left = sig
    right = np.roll(sig, 300)
    _write_wav(out_path, np.stack([left, right], axis=1) * 0.8)
    return out_path


def pick_music(repo_dir, total, workdir):
    folder = Path(repo_dir) / "assets" / "music"
    files = [p for p in folder.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")] if folder.exists() else []
    if files:
        return random.choice(files)
    return build_music(total, workdir / "music_bed.wav", seed=random.randint(1, 10_000))


def final_mix(video, voice_wav, music, sfx, captions, total, workdir, fmt_cfg, out_name="final.mp4"):
    maxrate_k = int(fmt_cfg["maxrate"].rstrip("k"))
    fc = (
        "[0:v]ass=captions.ass[v];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,dynaudnorm=f=150:g=15,asplit=2[voice][key];"
        "[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.32[mus];"
        "[mus][key]sidechaincompress=threshold=0.04:ratio=9:attack=15:release=450[duck];"
        "[3:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.45[fx];"
        "[voice][duck][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]"
    )
    _run(["ffmpeg", "-y", "-i", video.name, "-i", voice_wav.name,
          "-stream_loop", "-1", "-i", str(Path(music).resolve()), "-i", sfx.name,
          "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total + 0.3:.3f}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", str(fmt_cfg["crf"]),
          "-maxrate", fmt_cfg["maxrate"], "-bufsize", f"{maxrate_k * 2}k", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_name], cwd=workdir)
    return workdir / out_name


# ------------------------------------------------------------------ thumbnail

def _font(size, bold_path):
    from PIL import ImageFont
    for p in (bold_path, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def stock_photo(query, dst):
    if not PEXELS_KEY or not query:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search",
                         params={"query": query, "per_page": 15, "orientation": "landscape"},
                         headers={"Authorization": PEXELS_KEY, **UA}, timeout=30)
        photos = r.json().get("photos", []) if r.status_code == 200 else []
    except Exception:  # noqa
        return None
    for p in photos:
        if FEMALE_WORDS.search((p.get("alt") or "") + " " + (p.get("url") or "").replace("-", " ")):
            continue
        try:
            data = _get_bytes(p["src"]["large2x"])
        except Exception:  # noqa
            continue
        if shows_female([data]) is True:
            continue
        Path(dst).write_bytes(data)
        return dst
    return None


def make_thumbnail(prompt, text, query, workdir, bold_font=None, W=1280, H=720):
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
    base = workdir / "thumb_base.jpg"
    try:
        ai_image(prompt + ", ultra detailed, high contrast, vivid, dramatic rim light, one clear subject",
                 base, W, H)
    except Exception:  # noqa
        if not stock_photo(query, base):
            raise
    im = Image.open(base).convert("RGB")
    im = im.crop((0, 0, im.width, int(im.height * 0.92)))  # drop the generator's corner watermark
    # cover-crop
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    left, top = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((left, top, left + W, top + H))
    im = ImageEnhance.Contrast(im).enhance(1.25)
    im = ImageEnhance.Color(im).enhance(1.35)
    im = ImageEnhance.Sharpness(im).enhance(1.4)

    # left-to-right dark gradient + vignette
    grad = Image.new("L", (W, H))
    gd = ImageDraw.Draw(grad)
    for x in range(W):
        a = int(max(0, 235 * (1 - x / (W * 0.78))))
        gd.line([(x, 0), (x, H)], fill=a)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    im = Image.composite(black, im, grad)
    vig = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-W * 0.25, -H * 0.35, W * 1.25, H * 1.35], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    im = Image.composite(im, black, vig)

    d = ImageDraw.Draw(im)
    words = (text or "").upper().split()[:4]
    if len(words) >= 3:
        lines = [" ".join(words[:len(words) // 2]), " ".join(words[len(words) // 2:])]
    else:
        lines = [" ".join(words)] if words else []
    y = H * 0.18
    colors = [(255, 255, 255), (255, 212, 0)]
    for i, line in enumerate(lines):
        size = 160
        f = _font(size, bold_font)
        while d.textlength(line, font=f) > W * 0.60 and size > 60:
            size -= 6
            f = _font(size, bold_font)
        top_off = d.textbbox((0, 0), line, font=f, stroke_width=10)[1]
        d.text((60, y - top_off), line, font=f, fill=colors[i % 2] if len(lines) > 1 else colors[1],
               stroke_width=10, stroke_fill=(0, 0, 0))
        box = d.textbbox((60, y - top_off), line, font=f, stroke_width=10)
        y = box[3] + 14
    # red accent bar under the text + arrow pointing at the subject
    d.rectangle([60, y + 6, 60 + 220, y + 24], fill=(230, 20, 30))
    ax, ay = int(W * 0.50), int(min(y + 110, H * 0.82))
    d.polygon([(ax, ay - 46), (ax + 120, ay), (ax, ay + 46)], fill=(230, 20, 30), outline=(0, 0, 0))
    d.rectangle([ax - 110, ay - 16, ax, ay + 16], fill=(230, 20, 30))
    # brand tag sized to its text
    tag_font = _font(34, bold_font)
    tw = d.textlength("NOXVEILX", font=tag_font)
    tb = d.textbbox((0, 0), "NOXVEILX", font=tag_font)
    th = tb[3] - tb[1]
    x0, y0 = W - 30 - tw - 36, H - 30 - th - 24
    d.rounded_rectangle([x0, y0, W - 30, H - 30], radius=10, fill=(0, 0, 0))
    d.text((x0 + 18, y0 + 12 - tb[1]), "NOXVEILX", font=tag_font, fill=(255, 212, 0))
    out = workdir / "thumbnail.jpg"
    im.save(out, "JPEG", quality=92)
    return out
