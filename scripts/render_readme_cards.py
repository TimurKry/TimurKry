#!/usr/bin/env python3
"""Render every animated SVG card of the profile README into cards/ (light) and cards/dark/.

  python scripts/render_readme_cards.py            # animated
  STATIC=1 python scripts/render_readme_cards.py   # final frame only (for screenshots)

Reads config.json, data/contributions.json, data/repos.json.
Optional: put assets/portrait.jpg (or .png) to replace the monogram with an ASCII portrait.
"""
import base64
import datetime as dt
import html
import io
import json
import os
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
STATIC = os.environ.get("STATIC") == "1"
FONT_DIR = ROOT / "fonts"
OUT = ROOT / "cards"

# --------------------------------------------------------------------------- palette
THEMES = {
    "light": dict(paper="#F5F2EB", ink="#151514", muted="#6E6A62", line="#DDD7CA", cell0="#E6E0D3",
                  blue="#2D5BFF", red="#F0452B", yellow="#F6B800", on_blue="#FFFFFF", on_red="#FFFFFF",
                  on_yellow="#151514"),
    "dark": dict(paper="#121211", ink="#F2EEE6", muted="#8F8B83", line="#2A2926", cell0="#1F1E1C",
                 blue="#5A7DFF", red="#FF5A3D", yellow="#FFC61A", on_blue="#FFFFFF", on_red="#FFFFFF",
                 on_yellow="#151514"),
}


def mix(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


# --------------------------------------------------------------------------- fonts
FONTS = {  # css family -> file
    "S": "serif.woff2", "SI": "serif-italic.woff2", "G": "sans.woff2",
    "GB": "sans-semibold.woff2", "M": "mono.woff2",
}
_b64, _metrics = {}, {}


def font_css(families):
    rules = []
    for f in families:
        if f not in _b64:
            _b64[f] = base64.b64encode((FONT_DIR / FONTS[f]).read_bytes()).decode()
        rules.append(f"@font-face{{font-family:'{f}';src:url(data:font/woff2;base64,{_b64[f]}) format('woff2')}}")
    return "".join(rules)


def text_width(s, fam, size):
    if fam not in _metrics:
        t = TTFont(FONT_DIR / FONTS[fam])
        _metrics[fam] = (t.getBestCmap(), t["hmtx"].metrics, t["head"].unitsPerEm)
    cmap, hmtx, upm = _metrics[fam]
    w = 0
    for ch in s:
        g = cmap.get(ord(ch))
        w += hmtx[g][0] if g else upm * 0.5
    return w * size / upm


def wrap(s, fam, size, max_w, max_lines=2):
    words, lines, cur = s.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if text_width(test, fam, size) <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while text_width(lines[-1] + "…", fam, size) > max_w and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return [l for l in lines if l]


def esc(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------- svg shell
BASE_CSS = """
text{white-space:pre}
.S{font-family:'S',Georgia,serif}.SI{font-family:'SI',Georgia,serif;font-style:italic}
.G{font-family:'G',system-ui,sans-serif}.GB{font-family:'GB',system-ui,sans-serif;font-weight:600}
.M{font-family:'M',ui-monospace,monospace}
@keyframes up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
.up{animation:up .7s cubic-bezier(.2,.8,.2,1) both}
.fade{animation:fade .5s ease both}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def svg(w, h, body, families, css="", bg=None, th=None, defs=""):
    css_all = font_css(families) + BASE_CSS + css + ("*{animation:none!important}" if STATIC else "")
    shell = ""
    if bg is None and th is not None:
        shell = (f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="16" '
                 f'fill="{th["paper"]}" stroke="{th["line"]}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'fill="none"><defs><style>{css_all}</style>{defs}</defs>{shell}{body}</svg>')


def d(ms):  # animation-delay style
    return f'style="animation-delay:{int(ms)}ms"'


def countup(value, x, y, cls, size, fill, begin_ms, anchor="start", fmt="{:,}"):
    """Count-up number with SMIL <set> frames (CSS can't change text)."""
    if STATIC:
        return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{fill}" '
                f'text-anchor="{anchor}">{esc(fmt.format(value))}</text>')
    n, dur, out = 18, 900, []
    for i in range(n):
        t = i / (n - 1)
        v = round(value * (1 - (1 - t) ** 3))
        t0 = begin_ms + dur * i / n
        t1 = begin_ms + dur * (i + 1) / n
        sets = f'<set attributeName="visibility" to="visible" begin="{t0:.0f}ms" fill="freeze"/>'
        if i < n - 1:
            sets += f'<set attributeName="visibility" to="hidden" begin="{t1:.0f}ms" fill="freeze"/>'
        out.append(f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{fill}" '
                   f'text-anchor="{anchor}" visibility="hidden">{esc(fmt.format(v))}{sets}</text>')
    return "".join(out)


# --------------------------------------------------------------------------- data
def load_days():
    p = ROOT / "data" / "contributions.json"
    return json.loads(p.read_text()) if p.exists() else []


def stats(days):
    total = sum(x["count"] for x in days)
    best_day = max((x["count"] for x in days), default=0)
    longest = cur = run = 0
    for x in days:
        run = run + 1 if x["count"] > 0 else 0
        longest = max(longest, run)
    rev = list(reversed(days))
    if rev and rev[0]["count"] == 0:  # today not yet active -> streak may continue from yesterday
        rev = rev[1:]
    for x in rev:
        if x["count"] > 0:
            cur += 1
        else:
            break
    months = {}
    for x in days:
        months.setdefault(x["date"][:7], 0)
        months[x["date"][:7]] += x["count"]
    last12 = sorted(months.items())[-12:]
    return dict(total=total, best_day=best_day, longest=longest, current=cur, months=last12)


# --------------------------------------------------------------------------- 1. hero
RAMP = " .·:-=+*#%@"


def ascii_grid(cols, rows, invert):
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
    cw, ch = 6, 10
    W, H = cols * cw, rows * ch
    portrait = next((p for p in [ROOT / "assets/portrait.jpg", ROOT / "assets/portrait.png"] if p.exists()), None)
    if portrait:
        import numpy as np
        src = Image.open(portrait)
        fit = lambda x: ImageOps.fit(x, (W, H), centering=(0.5, 0.35))
        lum = np.asarray(fit(src.convert("L")), dtype=float) / 255
        mask = (np.asarray(fit(src.getchannel("A")), dtype=float) / 255
                if src.mode in ("RGBA", "LA") else np.ones_like(lum))
        inside = lum[mask > 0.5]
        lo, hi = np.percentile(inside, 3), np.percentile(inside, 97)
        tone = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)
        tone = tone if invert else 1 - tone          # dark theme: bright = dense; light: dark = dense
        tone = tone ** 1.35
        edges = np.asarray(fit(src.convert("L")).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3)),
                           dtype=float) / 255
        edges = np.clip(edges / max(np.percentile(edges[mask > 0.5], 97), 1e-3), 0, 1)
        v = np.clip(0.8 * tone + 0.35 * edges, 0, 1) * mask
        im = Image.fromarray((v * 255).astype("uint8"))
    else:
        t = TTFont(FONT_DIR / FONTS["S"])
        t.flavor = None
        buf = io.BytesIO()
        t.save(buf)
        raw = buf.getvalue()
        im = Image.new("L", (W, H), 0)
        dr = ImageDraw.Draw(im)
        size = int(H * 1.05)
        f = ImageFont.truetype(io.BytesIO(raw), size)
        while dr.textbbox((0, 0), CFG["monogram"], font=f)[2] > W * 0.86:
            size -= 4
            f = ImageFont.truetype(io.BytesIO(raw), size)
        bb = dr.textbbox((0, 0), CFG["monogram"], font=f)
        dr.text(((W - bb[2] - bb[0]) / 2, (H - bb[3] - bb[1]) / 2), CFG["monogram"], font=f, fill=255)
        halo = im.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.55))
        field = Image.new("L", (W, H), 0)
        fd = ImageDraw.Draw(field)
        for r in range(int(min(W, H) * 0.62), 0, -6):
            fd.ellipse([W / 2 - r * 1.15, H / 2 - r, W / 2 + r * 1.15, H / 2 + r],
                       fill=int(70 * (1 - r / (min(W, H) * 0.62))))
        from PIL import ImageChops
        im = ImageChops.lighter(ImageChops.lighter(im, halo), field)
    small = im.resize((cols, rows), Image.BOX)
    px = small.load()
    return [[px[c, r] / 255 for c in range(cols)] for r in range(rows)]


def hero(th):
    W, H = 840, 330
    cols, rows, fs, lh = 64, 33, 8.2, 8.5
    grid = ascii_grid(cols, rows, invert=th is THEMES["dark"])
    ox, oy = 26, 20
    rows_svg = []
    for r, row in enumerate(grid):
        spans, cur_cls, buf = [], None, ""
        for v in row:
            chx = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1) + 0.15))]
            cls = "i" if v > 0.62 else ("b" if v > 0.3 else "m")
            if cls != cur_cls and buf:
                spans.append(f'<tspan class="{cur_cls}">{esc(buf)}</tspan>')
                buf = ""
            cur_cls = cls
            buf += chx
        spans.append(f'<tspan class="{cur_cls}">{esc(buf)}</tspan>')
        rows_svg.append(f'<text class="M row" x="{ox}" y="{oy + (r + 1) * lh:.1f}" font-size="{fs}" '
                        f'{d(r * 22)}>{"".join(spans)}</text>')

    x = 382
    name = esc(CFG["name"])
    role_lines = wrap(CFG["role"], "GB", 19, W - x - 30, 1)
    tag_lines = wrap(CFG["tagline"], "G", 15, W - x - 34, 3)
    shine = "" if STATIC else (
        '<animateTransform attributeName="gradientTransform" type="translate" from="-1.2 0" to="1.2 0" '
        'dur="4.5s" begin="0.9s" repeatCount="indefinite"/>')
    defs = (f'<linearGradient id="sh" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">'
            f'<stop offset="0" stop-color="{th["ink"]}"/><stop offset=".42" stop-color="{th["ink"]}"/>'
            f'<stop offset=".5" stop-color="{th["blue"]}"/><stop offset=".58" stop-color="{th["ink"]}"/>'
            f'<stop offset="1" stop-color="{th["ink"]}"/>{shine}</linearGradient>')
    y = 66
    body = ["".join(rows_svg)]
    body.append(f'<text class="M up" x="{x}" y="{y}" font-size="12" fill="{th["muted"]}" letter-spacing="2" '
                f'{d(300)}>HELLO, I\'M</text>')
    body.append(f'<text class="S up" x="{x - 4}" y="{y + 92}" font-size="104" fill="url(#sh)" '
                f'letter-spacing="-2" {d(380)}>{name}</text>')
    y += 132
    for i, l in enumerate(role_lines):
        body.append(f'<text class="GB up" x="{x}" y="{y}" font-size="19" fill="{th["ink"]}" {d(520)}>{esc(l)}</text>')
    y += 28
    for i, l in enumerate(tag_lines):
        body.append(f'<text class="G up" x="{x}" y="{y + i * 21}" font-size="15" fill="{th["muted"]}" '
                    f'{d(600 + i * 60)}>{esc(l)}</text>')
    y = H - 34
    body.append(f'<line x1="{x}" y1="{y - 22}" x2="{W - 30}" y2="{y - 22}" stroke="{th["line"]}" class="draw" {d(800)}/>')
    body.append(f'<text class="M up" x="{x}" y="{y}" font-size="12" fill="{th["muted"]}" {d(860)}>'
                f'{esc(CFG["meta"])}</text>')
    hw = text_width(CFG["handle"], "M", 12)
    body.append(f'<text class="M up" x="{W - 30 - hw - 10}" y="{y}" font-size="12" fill="{th["ink"]}" '
                f'{d(900)}>{esc(CFG["handle"])}</text>')
    body.append(f'<rect class="cur" x="{W - 37}" y="{y - 10}" width="7" height="12" fill="{th["blue"]}"/>')
    css = f"""
.i{{fill:{th['ink']}}}.b{{fill:{th['blue']}}}.m{{fill:{th['muted']};opacity:.55}}
.row{{animation:fade .35s ease both}}
.draw{{stroke-dasharray:460;animation:dr 1s cubic-bezier(.6,0,.2,1) both}}
@keyframes dr{{from{{stroke-dashoffset:460}}to{{stroke-dashoffset:0}}}}
.cur{{animation:bl 1.1s steps(1) infinite}}@keyframes bl{{50%{{opacity:0}}}}
"""
    return svg(W, H, "".join(body), ["S", "G", "GB", "M"], css, th=th, defs=defs)


# --------------------------------------------------------------------------- 2. contribution graph
def graph(th, days, st):
    W, H = 840, 238
    cell, gap = 11, 3
    step = cell + gap
    if not days:
        days = [{"date": (dt.date.today() - dt.timedelta(days=i)).isoformat(), "count": 0, "level": 0}
                for i in range(364, -1, -1)]
    first = dt.date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    ncols = (lead + len(days) + 6) // 7
    gw = ncols * step - gap
    ox, oy = (W - gw) / 2, 112
    levels = [th["cell0"]] + [mix(th["cell0"], th["blue"], t) for t in (.3, .55, .8, 1)]
    cells, months_seen = [], {}
    for i, day in enumerate(days):
        k = i + lead
        c, r = k // 7, k % 7
        date = dt.date.fromisoformat(day["date"])
        if date.day <= 7 and r == 0 or (i == 0 and date.day <= 20):
            months_seen.setdefault((date.year, date.month), c)
        delay = 200 + c * 16 + r * 7
        cells.append(f'<rect class="c" x="{ox + c * step:.1f}" y="{oy + r * step}" width="{cell}" height="{cell}" '
                     f'rx="2.5" fill="{levels[day["level"]]}" {d(delay)}/>')
    labels = []
    for (yy, mm), c in months_seen.items():
        if c > ncols - 3:
            continue
        labels.append(f'<text class="M fade" x="{ox + c * step:.1f}" y="{oy - 10}" font-size="10" '
                      f'fill="{th["muted"]}" {d(150 + c * 16)}>{dt.date(yy, mm, 1).strftime("%b")}</text>')
    title = (f'<text class="M up" x="{ox}" y="40" font-size="11" fill="{th["muted"]}" letter-spacing="2">'
             f'CONTRIBUTIONS · LAST 12 MONTHS</text>')
    total = countup(st["total"], ox, 72, "S", 34, th["ink"], 250)
    tw = text_width(f'{st["total"]:,}', "S", 34)
    unit = (f'<text class="SI fade" x="{ox + tw + 10}" y="72" font-size="22" fill="{th["muted"]}" {d(1100)}>'
            f'commits, PRs &amp; reviews</text>')
    leg_x = ox + gw - 5 * step - 70
    legend = [f'<text class="M" x="{leg_x}" y="{oy + 7 * step + 18}" font-size="10" fill="{th["muted"]}">less</text>']
    for i, col in enumerate(levels):
        legend.append(f'<rect x="{leg_x + 30 + i * step}" y="{oy + 7 * step + 9}" width="{cell}" height="{cell}" '
                      f'rx="2.5" fill="{col}"/>')
    legend.append(f'<text class="M" x="{leg_x + 34 + 5 * step}" y="{oy + 7 * step + 18}" font-size="10" '
                  f'fill="{th["muted"]}">more</text>')
    sweep = "" if STATIC else (
        f'<rect class="sw" x="{ox - 40}" y="{oy - 4}" width="40" height="{7 * step + 4}" fill="url(#sg)"/>')
    defs = (f'<linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{th["blue"]}" stop-opacity="0"/>'
            f'<stop offset=".8" stop-color="{th["blue"]}" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="{th["blue"]}" stop-opacity="0"/></linearGradient>')
    css = f"""
.c{{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.3,1.6,.5,1) both}}
@keyframes pop{{from{{opacity:0;transform:scale(0)}}to{{opacity:1;transform:none}}}}
.sw{{animation:sw 1.3s cubic-bezier(.5,0,.5,1) .2s both}}
@keyframes sw{{from{{transform:translateX(0);opacity:1}}90%{{opacity:1}}to{{transform:translateX({gw + 40}px);opacity:0}}}}
"""
    body = title + total + unit + "".join(labels) + "".join(cells) + sweep + "".join(legend)
    return svg(W, H, body, ["S", "SI", "M"], css, th=th, defs=defs)


# --------------------------------------------------------------------------- 3. monthly activity
def activity(th, st):
    W, H = 840, 290
    body = [f'<text class="M up" x="32" y="44" font-size="11" fill="{th["muted"]}" letter-spacing="2">'
            f'ACTIVITY · BY MONTH</text>']
    items = [("total", "contributions"), ("best_day", "best single day"),
             ("longest", "longest streak, days"), ("current", "current streak, days")]
    for i, (k, label) in enumerate(items):
        cx, cy = 32 + (i % 2) * 140, 112 + (i // 2) * 96
        col = th["blue"] if k == "longest" else th["ink"]
        body.append(countup(st[k], cx, cy, "S", 44, col, 200 + i * 120))
        body.append(f'<text class="G up" x="{cx}" y="{cy + 22}" font-size="12" fill="{th["muted"]}" '
                    f'{d(300 + i * 120)}>{label}</text>')
    body.append(f'<line x1="318" y1="64" x2="318" y2="{H - 34}" stroke="{th["line"]}"/>')
    months = st["months"] or [(dt.date.today().strftime("%Y-%m"), 0)]
    mx = max((v for _, v in months), default=0) or 1
    best_i = max(range(len(months)), key=lambda i: months[i][1])
    x0, base, maxh = 350, H - 52, 170
    bw = (W - 30 - x0) / len(months)
    for i, (ym, v) in enumerate(months):
        h = max(3, v / mx * maxh)
        bx = x0 + i * bw + 7
        best = i == best_i and v > 0
        fill = th["blue"] if best else mix(th["paper"], th["ink"], .16)
        body.append(f'<rect class="bar" x="{bx:.1f}" y="{base - h:.1f}" width="{bw - 14:.1f}" height="{h:.1f}" '
                    f'rx="4" fill="{fill}" {d(450 + i * 60)}/>')
        lab = dt.date(int(ym[:4]), int(ym[5:]), 1).strftime("%b")
        body.append(f'<text class="M fade" x="{bx + (bw - 14) / 2:.1f}" y="{base + 20}" font-size="10" '
                    f'text-anchor="middle" fill="{th["ink"] if best else th["muted"]}" {d(450 + i * 60)}>{lab}</text>')
        if best:
            body.append(f'<text class="M up" x="{bx + (bw - 14) / 2:.1f}" y="{base - h - 10:.1f}" font-size="11" '
                        f'text-anchor="middle" fill="{th["blue"]}" {d(1300)}>{v} ★</text>')
    body.append(f'<line x1="{x0}" y1="{base + .5}" x2="{W - 30}" y2="{base + .5}" stroke="{th["line"]}"/>')
    css = """
.bar{transform-box:fill-box;transform-origin:bottom;animation:grow .8s cubic-bezier(.2,.9,.3,1.15) both}
@keyframes grow{from{transform:scaleY(0)}to{transform:none}}
"""
    return svg(W, H, "".join(body), ["S", "G", "M"], css, th=th)


# --------------------------------------------------------------------------- 4. tiles
def tile(th, t, idx):
    W, H = 272, 210
    bg, fg = th[t["color"]], th["on_" + t["color"]]
    base = 300 + idx * 140
    deco = {
        "blue": "".join(f'<rect x="{196 + c * 20}" y="{116 + r * 20}" width="13" height="13" rx="3" fill="{fg}" '
                        f'opacity="{.14 + .1 * ((c + r) % 3)}"/>' for c in range(3) for r in range(3)),
        "red": "".join(f'<circle cx="{W - 10}" cy="{H - 10}" r="{16 + i * 16}" stroke="{fg}" stroke-width="1.5" '
                       f'opacity="{.4 - i * .08}"/>' for i in range(5)),
        "yellow": "".join(f'<rect x="196" y="{118 + i * 13}" width="{54 - (i * 17) % 34}" height="5" rx="2.5" '
                          f'fill="{fg}" opacity=".22"/>' for i in range(5)),
    }[t["color"]]
    title_lines = wrap(t["title"], "S", 34, W - 44, 2)
    body = [f'<g class="tile" {d(base)}><rect width="{W}" height="{H}" rx="18" fill="{bg}"/>',
            f'<g clip-path="url(#cl)">{deco}',
            '' if STATIC else f'<circle class="ring" cx="{W}" cy="0" r="330" stroke="{fg}" stroke-width="2" {d(base + 1600)}/>',
            '' if STATIC else f'<rect class="shine" x="-120" y="-20" width="70" height="{H + 40}" fill="url(#sh)" '
                              f'transform="skewX(-18)" {d(base + 2400)}/>',
            '</g>',
            f'<text class="M" x="22" y="34" font-size="11" fill="{fg}" letter-spacing="2.5" opacity=".85">'
            f'{esc(t["label"])}</text>',
            f'<text class="G arrow" x="{W - 22}" y="38" font-size="22" fill="{fg}" text-anchor="end">↗</text>']
    for i, l in enumerate(title_lines):
        body.append(f'<text class="S" x="20" y="{96 + i * 36}" font-size="36" fill="{fg}" letter-spacing="-.5">{esc(l)}</text>')
    body.append(f'<text class="G" x="22" y="{H - 24}" font-size="12.5" fill="{fg}" opacity=".85">{esc(t["text"])}</text>')
    body.append('</g>')
    defs = (f'<clipPath id="cl"><rect width="{W}" height="{H}" rx="18"/></clipPath>'
            f'<linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" '
            f'stop-opacity="0"/></linearGradient>')
    css = """
.tile{transform-box:fill-box;transform-origin:50% 100%;animation:swing 1.1s cubic-bezier(.2,.8,.2,1) both}
@keyframes swing{0%{opacity:0;transform:translateY(60px) rotate(-5deg)}55%{opacity:1;transform:translateY(-8px) rotate(1.2deg)}
75%{transform:translateY(3px) rotate(-.4deg)}100%{transform:none}}
.ring{transform-box:fill-box;transform-origin:center;animation:ring 7s ease-out infinite both}
@keyframes ring{0%{transform:scale(0);opacity:.7}25%{transform:scale(1);opacity:0}100%{transform:scale(1);opacity:0}}
.shine{animation:shine 7s ease-in-out infinite both}
@keyframes shine{0%{transform:skewX(-18deg) translateX(0)}22%{transform:skewX(-18deg) translateX(520px)}100%{transform:skewX(-18deg) translateX(520px)}}
.arrow{animation:nudge 3.5s ease-in-out infinite}
@keyframes nudge{0%,80%,100%{transform:none}88%{transform:translate(3px,-3px)}}
"""
    return svg(W, H, "".join(body), ["S", "G", "M"], css, bg=bg, defs=defs)


# --------------------------------------------------------------------------- 5. repo cards
LANG = {"TypeScript": "#3178C6", "JavaScript": "#F1E05A", "Python": "#3572A5", "HTML": "#E34C26",
        "CSS": "#663399", "Java": "#B07219", "C++": "#F34B7D", "Vue": "#41B883", "Svelte": "#FF3E00",
        "Astro": "#FF5A03", "MDX": "#FCB32C", "Shell": "#89E051"}


def repo_card(th, r, live, idx):
    W, H = 412, 160
    info = {**{k: v for k, v in r.items() if v}, **{k: v for k, v in live.get(r["name"], {}).items() if v}}
    desc = info.get("description") or "Project by " + CFG["handle"]
    lang = info.get("language", "")
    base = 200 + idx * 120
    name_size = 32
    while text_width(r["name"], "S", name_size) > W - 80 and name_size > 20:
        name_size -= 1
    nw = text_width(r["name"], "S", name_size)
    body = [f'<g class="up" {d(base)}>',
            f'<text class="M" x="24" y="36" font-size="10.5" fill="{th["muted"]}" letter-spacing="2">'
            f'REPO {idx + 1:02d}</text>',
            f'<text class="G arrow" x="{W - 24}" y="40" font-size="20" fill="{th["ink"]}" text-anchor="end">↗</text>',
            f'<text class="S" x="22" y="{40 + name_size + 4}" font-size="{name_size}" fill="{th["ink"]}" '
            f'letter-spacing="-.3">{esc(r["name"])}</text>',
            f'<line class="ul" x1="24" y1="{50 + name_size}" x2="{24 + nw}" y2="{50 + name_size}" '
            f'stroke="{th["blue"]}" stroke-width="2" {d(base + 300)}/>']
    for i, l in enumerate(wrap(desc, "G", 13.5, W - 48, 2)):
        body.append(f'<text class="G" x="24" y="{86 + name_size - 10 + i * 19}" font-size="13.5" fill="{th["muted"]}">{esc(l)}</text>')
    fy = H - 22
    fx = 24
    if lang:
        body.append(f'<circle cx="{fx + 5}" cy="{fy - 4}" r="5" fill="{LANG.get(lang, th["blue"])}"/>')
        body.append(f'<text class="M" x="{fx + 16}" y="{fy}" font-size="11" fill="{th["ink"]}">{esc(lang)}</text>')
        fx += 30 + text_width(lang, "M", 11)
    if info.get("stars"):
        body.append(f'<text class="M" x="{fx}" y="{fy}" font-size="11" fill="{th["ink"]}">★ {info["stars"]}</text>')
    body.append('</g>')
    css = f"""
.ul{{stroke-dasharray:400;animation:dr .9s cubic-bezier(.6,0,.2,1) both}}
@keyframes dr{{from{{stroke-dashoffset:400}}to{{stroke-dashoffset:0}}}}
.arrow{{animation:nudge 3.5s ease-in-out infinite}}
@keyframes nudge{{0%,80%,100%{{transform:none}}88%{{transform:translate(3px,-3px)}}}}
"""
    return svg(W, H, "".join(body), ["S", "G", "M"], css, th=th)


# --------------------------------------------------------------------------- main
def main():
    days = load_days()
    st = stats(days)
    live_p = ROOT / "data" / "repos.json"
    live = json.loads(live_p.read_text()) if live_p.exists() else {}
    for theme, th in THEMES.items():
        out = OUT if theme == "light" else OUT / "dark"
        out.mkdir(parents=True, exist_ok=True)
        files = {"hero.svg": hero(th), "graph.svg": graph(th, days, st), "activity.svg": activity(th, st)}
        for i, t in enumerate(CFG["tiles"]):
            files[f'tile-{t["id"]}.svg'] = tile(th, t, i)
        for i, r in enumerate(CFG["repos"]):
            files[f'repo-{r["name"]}.svg'] = repo_card(th, r, live, i)
        for name, content in files.items():
            (out / name).write_text(content)
        print(f"{theme}: {len(files)} cards -> {out.relative_to(ROOT)}")
    write_readme()


def write_readme():
    u = CFG["username"]

    def pic(name, width=None, alt=""):
        w = f' width="{width}"' if width else ""
        return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="./cards/dark/{name}">'
                f'<img src="./cards/{name}"{w} alt="{esc(alt)}"></picture>')

    tiles = "\n".join(f'<a href="{esc(t["url"])}">{pic("tile-" + t["id"] + ".svg", "32.5%", t["label"])}</a>'
                      for t in CFG["tiles"])
    repos = CFG["repos"]
    repo_rows = []
    for i in range(0, len(repos), 2):
        pair = repos[i:i + 2]
        repo_rows.append("\n".join(
            f'<a href="https://github.com/{u}/{r["name"]}">{pic("repo-" + r["name"] + ".svg", "49.5%", r["name"])}</a>'
            for r in pair))
    readme = f"""<!-- generated by scripts/render_readme_cards.py — edit config.json, not this file -->
<p align="center">
{pic("hero.svg", "100%", CFG["name"] + " — " + CFG["role"])}
</p>

<p align="center">
{pic("graph.svg", "100%", "Contribution graph")}
</p>

<p align="center">
{pic("activity.svg", "100%", "Monthly activity")}
</p>

<p align="center">
{tiles}
</p>

<p align="center">
{(chr(10) + "<br>" + chr(10)).join(repo_rows)}
</p>
"""
    (ROOT / "README.md").write_text(readme)
    print("README.md written")


if __name__ == "__main__":
    main()
