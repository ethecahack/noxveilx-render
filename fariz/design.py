#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FARIZ KANAAN — محرك التصميم.
يبني كل شريحة كصفحة HTML (نص عربي حقيقي بخطوط مضمّنة، اتجاه RTL)
ثم يصوّرها بمتصفح Chromium إلى PNG/JPG. الخلفية صورة سينمائية داكنة
(Pollinations) أو تدرّج احتياطي إذا تعذّر توليدها.
"""
import base64
import hashlib
import html
import os
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
ASSETS = HERE / "assets"
ICONS = ASSETS / "icons"

# ---------------- الهوية (مأخوذة من المنشورين الأول والثاني) ----------------
INK = "#0A0C10"
GOLD = "#C99A6A"
GOLD_LIGHT = "#E6C893"
GOLD_DEEP = "#8A6438"
CREAM = "#E2D2C2"
BODY = "#BDB6AC"
MUTED = "#8C857C"

BG_STYLE = (
    "dark cinematic scene, antique and historical mood, warm golden candlelight, "
    "sepia and deep brown tones, low-key lighting, deep black shadows, "
    "the main subjects placed at the far left and far right edges, "
    "large empty dark area in the center, highly detailed, photorealistic, "
    "no text, no letters, no writing, no watermark, no logo, no people, no faces"
)


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def font_css() -> str:
    out = []
    for w in (300, 400, 500, 700, 800, 900):
        for sub, rng in (("arabic", "U+0600-06FF,U+0750-077F,U+08A0-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200C-200F,U+060C,U+061B,U+061F"),
                         ("latin", "U+0000-00FF,U+2000-206F,U+2190-21FF")):
            f = FONTS / f"noto-sans-arabic-{sub}-{w}-normal.woff2"
            if f.exists():
                out.append(f"@font-face{{font-family:'FK Arabic';font-weight:{w};src:url(data:font/woff2;base64,{_b64(f)}) format('woff2');unicode-range:{rng};}}")
    for w in (400, 500, 600, 700):
        f = FONTS / f"cinzel-latin-{w}-normal.woff2"
        if f.exists():
            out.append(f"@font-face{{font-family:'FK Serif';font-weight:{w};src:url(data:font/woff2;base64,{_b64(f)}) format('woff2');}}")
    return "\n".join(out)


_FONT_CSS = None
_IMG_CACHE = {}


def img_uri(path: Path) -> str:
    key = str(path)
    if key not in _IMG_CACHE:
        mime = "image/png" if path.suffix == ".png" else "image/jpeg"
        _IMG_CACHE[key] = f"data:{mime};base64,{_b64(path)}"
    return _IMG_CACHE[key]


def icon_svg(name: str, size: int = 44) -> str:
    p = ICONS / f"{name}.svg"
    if not p.exists():
        p = ICONS / "scroll.svg"
    svg = p.read_text(encoding="utf-8")
    svg = svg.replace('stroke="currentColor"', f'stroke="{GOLD}"').replace('stroke-width="2"', 'stroke-width="1.4"')
    svg = svg.replace('width="24"', f'width="{size}"').replace('height="24"', f'height="{size}"')
    return svg


def esc(s) -> str:
    return html.escape(str(s or ""))


# ---------------- الخلفيات ----------------

def fetch_background(prompt: str, w: int, h: int, out: Path, seed: int = None) -> Path:
    """يولّد خلفية سينمائية عبر Pollinations (مجاني). يرجع None لو فشل."""
    if out.exists() and out.stat().st_size > 20000:
        return out
    if os.environ.get("FK_NO_NET") == "1":
        return None
    seed = seed if seed is not None else int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
    full = f"{prompt}, {BG_STYLE}"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(full) +
           f"?width={w}&height={h}&nologo=true&model=flux&seed={seed}")
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fariz-kanaan-studio/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if len(data) > 20000:
                out.write_bytes(data)
                return out
        except Exception as e:  # noqa
            print(f"  background attempt {attempt + 1} failed: {e}", flush=True)
        time.sleep(6 + attempt * 6)
    return None


def bg_css(bg: Path) -> str:
    if bg and bg.exists():
        return f"background:{INK} url('{img_uri(bg)}') center/cover no-repeat;"
    # احتياطي: تدرّج دافئ داكن
    return (f"background: radial-gradient(ellipse at 18% 40%, #3a2a1a 0%, transparent 45%),"
            f"radial-gradient(ellipse at 85% 55%, #33261a 0%, transparent 42%),"
            f"radial-gradient(ellipse at 50% 100%, #1d1712 0%, transparent 60%), {INK};")


# ---------------- CSS المشترك ----------------

def base_css(w: int, h: int) -> str:
    global _FONT_CSS
    if _FONT_CSS is None:
        _FONT_CSS = font_css()
    return _FONT_CSS + f"""
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{w}px;height:{h}px;overflow:hidden;background:{INK}}}
body{{font-family:'FK Arabic',sans-serif;color:{CREAM};direction:rtl;-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision}}
.stage{{position:relative;width:{w}px;height:{h}px;overflow:hidden}}
.bg{{position:absolute;inset:0}}
.shade{{position:absolute;inset:0;background:
  radial-gradient(ellipse 46% 58% at 50% 46%, rgba(8,9,12,.86) 0%, rgba(8,9,12,.62) 55%, rgba(8,9,12,.12) 100%),
  linear-gradient(180deg, rgba(8,9,12,.55) 0%, rgba(8,9,12,0) 22%, rgba(8,9,12,0) 70%, rgba(8,9,12,.92) 100%)}}
.content{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center}}
.brand{{display:flex;flex-direction:column;align-items:center;gap:6px}}
.brand img.logo{{display:block}}
.brand .name{{font-family:'FK Serif',serif;font-weight:500;letter-spacing:.2em;color:{CREAM};direction:ltr;margin-right:-.2em}}
.brand .roles{{color:{BODY};font-weight:400}}
.div{{display:flex;align-items:center;justify-content:center;gap:14px;color:{GOLD}}}
.div i{{display:block;height:1px;background:linear-gradient(90deg,transparent,{GOLD_DEEP},transparent)}}
.div b{{font-size:15px;line-height:1;color:{GOLD_LIGHT};font-weight:400}}
.h1{{font-weight:800;color:{CREAM};text-align:center;line-height:1.25;text-shadow:0 3px 18px rgba(0,0,0,.65)}}
.h2{{font-weight:900;text-align:center;line-height:1.3;
  background:linear-gradient(180deg,{GOLD_LIGHT} 0%,{GOLD} 55%,{GOLD_DEEP} 100%);-webkit-background-clip:text;background-clip:text;color:transparent;
  filter:drop-shadow(0 3px 12px rgba(0,0,0,.7))}}
.sub{{color:{CREAM};text-align:center;font-weight:400;opacity:.92;line-height:1.6}}
.boxlabel{{border:1px solid {GOLD_DEEP};color:{GOLD_LIGHT};padding:8px 30px;font-weight:500;background:rgba(10,12,16,.45)}}
.gold{{color:{GOLD_LIGHT}}}
.footer{{position:absolute;left:50%;transform:translateX(-50%);display:block}}
.idx{{position:absolute;top:34px;left:40px;font-family:'FK Serif',serif;color:{GOLD};font-size:20px;letter-spacing:.18em;direction:ltr}}
.swipe{{position:absolute;bottom:150px;left:52px;color:{GOLD_LIGHT};font-size:22px;font-weight:500;display:flex;align-items:center;gap:10px;opacity:.95}}
.points{{display:grid;column-gap:34px;row-gap:26px;direction:rtl}}
.pt{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px}}
.pt .ic{{width:76px;height:76px;border-radius:50%;border:1px solid {GOLD_DEEP};display:flex;align-items:center;justify-content:center;background:rgba(10,12,16,.55)}}
.pt .t{{color:{GOLD};font-weight:700;font-size:25px;line-height:1.35}}
.pt .d{{color:{CREAM};opacity:.9;font-size:19.5px;line-height:1.6;font-weight:400}}
.quote{{position:relative;border:1px solid {GOLD_DEEP};border-top:none;padding:14px 46px 16px;text-align:center;color:{CREAM};font-weight:500;background:rgba(10,12,16,.4)}}
.quote:before,.quote:after{{position:absolute;font-family:'FK Serif',serif;color:{GOLD};font-size:64px;line-height:1}}
.quote:before{{content:'\\201C';top:-30px;right:-22px}}
.quote:after{{content:'\\201D';bottom:-42px;left:-22px}}
.rows{{display:flex;flex-direction:column;gap:12px}}
.row{{display:flex;align-items:center;gap:22px;border-bottom:1px solid rgba(138,100,56,.45);padding:8px 6px 12px}}
.row .k{{font-family:'FK Serif','FK Arabic',serif;color:{GOLD_LIGHT};font-weight:700;font-size:32px;min-width:120px;text-align:center;direction:rtl;unicode-bidi:plaintext}}
.row .v{{color:{CREAM};font-size:25px;font-weight:500;line-height:1.45}}
.row .v small{{display:block;color:{BODY};font-size:18px;font-weight:400}}
.opts{{display:grid;grid-template-columns:1fr 1fr;gap:18px 22px}}
.opt{{border:1px solid {GOLD_DEEP};background:rgba(10,12,16,.55);padding:18px 22px;display:flex;align-items:center;gap:16px;font-size:27px;font-weight:600;color:{CREAM}}}
.opt b{{width:46px;height:46px;border-radius:50%;border:1px solid {GOLD};color:{GOLD_LIGHT};display:flex;align-items:center;justify-content:center;font-size:24px;flex:none}}
.para{{color:{CREAM};font-size:27px;line-height:1.75;text-align:center;font-weight:400}}
.para b{{color:{GOLD_LIGHT};font-weight:700}}
.stat{{font-family:'FK Serif',serif;font-weight:600;color:{GOLD_LIGHT};direction:ltr;line-height:1;text-shadow:0 4px 18px rgba(0,0,0,.7)}}
.cap{{display:inline-block;background:rgba(8,9,12,.78);border:1px solid rgba(138,100,56,.6);padding:14px 30px 18px;color:{CREAM};font-weight:700;text-align:center;line-height:1.5}}
.cap em{{font-style:normal;color:{GOLD_LIGHT}}}
"""


def divider(width=520, gap=14):
    half = (width - 40) // 2
    return f'<div class="div" style="gap:{gap}px"><i style="width:{half}px"></i><b>✦</b><i style="width:{half}px"></i></div>'


def brand_block(scale=1.0, roles=True):
    lh = int(92 * scale)
    out = [f'<div class="brand"><img class="logo" src="{img_uri(ASSETS / "logo_f.png")}" style="height:{lh}px">',
           f'<div class="name" style="font-size:{int(27 * scale)}px">FARIZ KANAAN</div>']
    if roles:
        out.append(f'<div class="roles" style="font-size:{int(16 * scale)}px">باحث | كاتب | مفكر</div>')
    out.append("</div>")
    return "".join(out)


def footer_img(width=940, bottom=6):
    return f'<img class="footer" src="{img_uri(ASSETS / "footer.png")}" style="width:{width}px;bottom:{bottom}px">'


def page(w, h, bg, inner, extra_css=""):
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{base_css(w, h)}{extra_css}</style></head>'
            f'<body><div class="stage"><div class="bg" style="{bg_css(bg)}"></div><div class="shade"></div>{inner}</div></body></html>')


# ---------------- قوالب المربع 1080×1080 ----------------

def headline(sl, s1=70, s2=92):
    out = []
    if sl.get("headline"):
        out.append(f'<div class="h1" style="font-size:{sl.get("h1_size", s1)}px">{esc(sl["headline"])}</div>')
    if sl.get("headline_gold"):
        g = sl["headline_gold"]
        n = len(g)
        auto = s2 if n <= 15 else max(int(s2 * 15 / n * 1.12), int(s2 * 0.6))
        out.append(f'<div class="h2" style="font-size:{sl.get("h2_size", auto)}px;margin-top:-4px">{esc(g)}</div>')
    return "".join(out)


def rich(s):
    """**نص** يصبح ذهبيًا عريضًا."""
    t = esc(s)
    parts = t.split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def square_slide(sl: dict, bg: Path, idx: str = "", swipe: bool = False) -> str:
    lay = sl.get("layout", "cover")
    top = f'<div style="height:30px"></div>{brand_block()}<div style="height:12px"></div>{divider(500)}'
    body = ""
    if lay == "cover":
        body = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:0 70px 150px">'
                f'{headline(sl, 78, 112)}<div style="height:6px"></div>{divider(560)}'
                f'{f"<div class=sub style=font-size:29px;max-width:820px>{esc(sl.get('sub'))}</div>" if sl.get("sub") else ""}'
                f'{f"<div class=boxlabel style=font-size:24px;margin-top:10px>{esc(sl.get('label'))}</div>" if sl.get("label") else ""}'
                f'</div>')
    elif lay == "points":
        pts = sl.get("points", [])
        cols = 3 if len(pts) in (3, 5, 6) else 2
        cw = 290 if cols == 3 else 380
        cells = "".join(
            f'<div class="pt" style="width:{cw}px"><div class="ic">{icon_svg(p.get("icon", "scroll"), 40)}</div>'
            f'<div class="t">{esc(p.get("title"))}</div><div class="d">{esc(p.get("text"))}</div></div>' for p in pts)
        body = (f'<div style="display:flex;flex-direction:column;align-items:center;gap:12px;padding:14px 60px 0">{headline(sl, 54, 74)}'
                f'{f"<div class=sub style=font-size:24px>{esc(sl.get('sub'))}</div>" if sl.get("sub") else ""}</div>'
                f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding-bottom:140px">'
                f'{f"<div class=boxlabel style=font-size:24px>{esc(sl.get('label'))}</div>" if sl.get("label") else ""}'
                f'<div class="points" style="grid-template-columns:repeat({cols},{cw}px)">{cells}</div></div>')
    elif lay == "text":
        stat = f'<div class="stat" style="font-size:{sl.get("stat_size", 120)}px">{esc(sl["stat"])}</div>' if sl.get("stat") else ""
        statl = f'<div class="sub gold" style="font-size:26px;margin-top:-6px">{esc(sl.get("stat_label"))}</div>' if sl.get("stat_label") else ""
        ic = f'<div class="pt"><div class="ic" style="width:96px;height:96px">{icon_svg(sl["icon"], 50)}</div></div>' if sl.get("icon") else ""
        body = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:0 96px 150px">'
                f'{ic}{headline(sl, 60, 80)}{stat}{statl}{divider(420)}<div class="para" style="max-width:860px">{rich(sl.get("text"))}</div></div>')
    elif lay == "list":
        rows = "".join(f'<div class="row"><div class="k">{esc(r.get("k"))}</div><div class="v">{esc(r.get("v"))}'
                       f'{f"<small>{esc(r.get('note'))}</small>" if r.get("note") else ""}</div></div>' for r in sl.get("rows", []))
        body = (f'<div style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:12px 60px 0">{headline(sl, 50, 70)}</div>'
                f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 120px 150px;width:100%"><div class="rows">{rows}</div>'
                f'{f"<div class=sub style=font-size:21px;margin-top:16px;color:{GOLD_LIGHT}>{esc(sl.get('note'))}</div>" if sl.get("note") else ""}</div>')
    elif lay == "quiz":
        letters = ["أ", "ب", "ج", "د"]
        opts = "".join(f'<div class="opt"><b>{letters[i]}</b><span>{esc(o)}</span></div>' for i, o in enumerate(sl.get("options", [])[:4]))
        body = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;padding:0 80px 150px">'
                f'<div class="boxlabel" style="font-size:24px">{esc(sl.get("label", "اختبر معلوماتك"))}</div>{headline(sl, 52, 64)}'
                f'<div class="opts" style="width:880px">{opts}</div>'
                f'<div class="sub" style="font-size:23px;color:{GOLD_LIGHT}">{esc(sl.get("sub", "اكتب جوابك في التعليقات"))}</div></div>')
    elif lay == "close":
        body = (f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:30px;padding:0 90px 150px">'
                f'{headline(sl, 56, 76)}<div class="quote" style="font-size:32px;max-width:860px">{esc(sl.get("quote"))}</div>'
                f'{f"<div class=sub style=font-size:25px;margin-top:18px>{esc(sl.get('sub'))}</div>" if sl.get("sub") else ""}</div>')
    idx_html = f'<div class="idx">{esc(idx)}</div>' if idx else ""
    sw = '<div class="swipe">اسحب <span style="font-size:26px">←</span></div>' if swipe else ""
    q = ""
    if sl.get("quote") and lay not in ("close",):
        q = f'<div style="position:absolute;bottom:150px;left:0;right:0;display:flex;justify-content:center"><div class="quote" style="font-size:27px">{esc(sl["quote"])}</div></div>'
    inner = f'<div class="content">{top}{body}</div>{q}{idx_html}{sw}{footer_img()}'
    return page(1080, 1080, bg, inner)


# ---------------- قوالب العمودي 1080×1920 ----------------

def reel_cover(c: dict, bg: Path) -> str:
    inner = (f'<div class="content"><div style="height:250px"></div>{brand_block(1.35)}<div style="height:18px"></div>{divider(620)}'
             f'<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;padding:0 80px 420px">'
             f'{headline(c, 92, 132)}{divider(600)}'
             f'{f"<div class=sub style=font-size:36px;max-width:880px>{esc(c.get('sub'))}</div>" if c.get("sub") else ""}'
             f'<div class="boxlabel" style="font-size:28px;margin-top:14px">▶ {esc(c.get("label", "شاهد القصة"))}</div></div></div>'
             f'{footer_img(980, 250)}')
    css = ".shade{background:radial-gradient(ellipse 60% 42% at 50% 46%, rgba(8,9,12,.85) 0%, rgba(8,9,12,.55) 60%, rgba(8,9,12,.15) 100%),linear-gradient(180deg, rgba(8,9,12,.6) 0%, rgba(8,9,12,0) 20%, rgba(8,9,12,0) 68%, rgba(8,9,12,.95) 100%)}"
    return page(1080, 1920, bg, inner, css)


def reel_frame() -> str:
    """طبقة شفافة ثابتة فوق الفيديو: العلامة أعلى + تدرّج سفلي."""
    css = base_css(1080, 1920) + "html,body{background:transparent}"
    inner = (f'<div class="stage"><div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(8,9,12,.72) 0%,rgba(8,9,12,0) 16%,rgba(8,9,12,0) 55%,rgba(8,9,12,.78) 82%,rgba(8,9,12,.9) 100%)"></div>'
             f'<div style="position:absolute;top:150px;left:0;right:0;display:flex;justify-content:center">{brand_block(0.95, roles=False)}</div></div>')
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{inner}</body></html>'


def reel_caption(text: str, gold_words=()) -> str:
    css = base_css(1080, 1920) + "html,body{background:transparent}"
    words = esc(text).split()
    t = " ".join(f"<em>{w}</em>" if w in gold_words else w for w in words)
    inner = (f'<div class="stage"><div style="position:absolute;top:1180px;left:70px;right:70px;display:flex;justify-content:center">'
             f'<div class="cap" style="font-size:58px;max-width:940px">{t}</div></div></div>')
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{inner}</body></html>'


def reel_end(c: dict, bg: Path) -> str:
    inner = (f'<div class="content" style="justify-content:center;gap:26px;padding-bottom:300px">{brand_block(1.8)}{divider(640)}'
             f'<div class="h2" style="font-size:78px">{esc(c.get("end_line", "من سوريا... تبدأ الحكاية."))}</div>'
             f'<div class="sub" style="font-size:38px">تابع <span class="gold" style="font-family:\'FK Serif\';direction:ltr;display:inline-block">@fariz.kanaan</span></div></div>{footer_img(980, 250)}')
    return page(1080, 1920, bg, inner)


# ---------------- التصوير ----------------

class Renderer:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(args=["--font-render-hinting=none"])

    def shot(self, html_str: str, out: Path, w: int, h: int, transparent=False, jpeg=False):
        pg = self.browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.set_content(html_str, wait_until="load")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(120)
        if jpeg:
            pg.screenshot(path=str(out), type="jpeg", quality=93, full_page=False)
        else:
            pg.screenshot(path=str(out), omit_background=transparent, full_page=False)
        pg.close()
        return out

    def close(self):
        self.browser.close()
        self._pw.stop()
