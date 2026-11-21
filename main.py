#!/usr/bin/env python3
"""PERPETUA K-1 — the self-refilling kettle.

A studio catalogue photograph, rendered entirely with Pillow, of an
impossible gadget: a brushed-steel electric kettle caught mid-use,
pouring water *up* out of its own spout, over its open top, and back
into itself — so it never needs filling. One accessory: an empty white
mug, waiting beside it, that will never get its tea.

Writes /output/entry.png (1024 x 1024). Deterministic: fixed seed.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- setup

SEED = 20261121
rng = random.Random(SEED)

W = H = 1024          # final size
S = 2                 # supersampling factor
CW, CH = W * S, H * S

OUT = os.environ.get("ENTRY_OUT", "/output/entry.png")


def sc(v):
    """Scale a 1024-space scalar to canvas space."""
    return v * S


def box(x0, y0, x1, y1):
    return [x0 * S, y0 * S, x1 * S, y1 * S]


def pt(x, y):
    return (x * S, y * S)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def smoothstep(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def gauss(x, mu, sig):
    return math.exp(-((x - mu) ** 2) / (2 * sig * sig))


# ---------------------------------------------------------------- fonts

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-{w}.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans{w}.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-{w}.ttf",
]


def get_font(px, bold=False):
    w = "Bold" if bold else "Regular"
    for cand in _FONT_CANDIDATES:
        path = cand.format(w=w)
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, int(px * S))
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=int(px * S))
    except Exception:
        return ImageFont.load_default()


def draw_tracked(draw, cx, y, text, font, fill, tracking):
    """Draw letterspaced text centred on cx at top y. Returns its height."""
    widths = []
    total = 0.0
    for ch in text:
        wch = draw.textlength(ch, font=font)
        widths.append(wch)
        total += wch + tracking
    total -= tracking
    x = cx * S - total / 2
    asc, desc = font.getmetrics()
    for ch, wch in zip(text, widths):
        draw.text((x, y * S), ch, font=font, fill=fill)
        x += wch + tracking
    return (asc + desc) / S


# ---------------------------------------------------------------- backdrop

def make_background():
    """Seamless studio sweep: warm light grey, glow behind the product."""
    img = Image.new("RGB", (CW, CH))
    d = ImageDraw.Draw(img)
    top = (216, 213, 208)
    mid = (233, 231, 227)
    floor = (226, 223, 218)
    horizon = 0.70  # where wall melts into floor
    for j in range(CH):
        t = j / CH
        if t < horizon:
            c = mix(top, mid, smoothstep(t / horizon))
        else:
            c = mix(mid, floor, smoothstep((t - horizon) / (1 - horizon)))
        d.line([(0, j), (CW, j)], fill=c)
    # soft glow behind the hero
    glow = Image.new("L", (CW, CH), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse(box(90, 120, 900, 760), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(180 * S // 2))
    img = Image.composite(Image.new("RGB", (CW, CH), (246, 245, 242)), img, glow)
    # gentle vignette
    vig = Image.new("L", (CW, CH), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse(box(-260, -200, 1284, 1180), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160 * S // 2))
    dark = Image.new("RGB", (CW, CH), (196, 193, 188))
    img = Image.composite(img, dark, vig)
    return img


def soft_shadow(img, cx, cy, rx, ry, alpha, blur, dx=0, dy=0):
    layer = Image.new("L", (CW, CH), 0)
    d = ImageDraw.Draw(layer)
    d.ellipse(box(cx - rx + dx, cy - ry + dy, cx + rx + dx, cy + ry + dy), fill=alpha)
    layer = layer.filter(ImageFilter.GaussianBlur(blur * S // 2))
    black = Image.new("RGB", (CW, CH), (40, 38, 36))
    return Image.composite(black, img, layer)


# ---------------------------------------------------------------- kettle

KCX = 432.0          # kettle centre x
KBOT = 788.0         # kettle base y
KTOP = 438.0         # rim y
FLOOR = 788.0


def kettle_halfwidth(t):
    """Half-width of the body at height fraction t (0 bottom, 1 rim)."""
    keys = [
        (0.00, 170), (0.04, 174), (0.15, 175), (0.40, 171),
        (0.65, 164), (0.82, 150), (0.93, 126), (1.00, 110),
    ]
    for i in range(len(keys) - 1):
        t0, w0 = keys[i]
        t1, w1 = keys[i + 1]
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            return lerp(w0, w1, smoothstep(u))
    return keys[-1][1]


def kettle_silhouette():
    pts = []
    n = 60
    for i in range(n + 1):
        t = i / n
        y = lerp(KBOT, KTOP, t)
        pts.append(pt(KCX - kettle_halfwidth(t), y))
    for i in range(n, -1, -1):
        t = i / n
        y = lerp(KBOT, KTOP, t)
        pts.append(pt(KCX + kettle_halfwidth(t), y))
    return pts


def steel_column(u):
    """Brushed-steel colour for a normalised cylinder position u in [0,1].

    Key light from the upper left: bright band left of centre, long fall
    to a darker right edge, thin dark seams at both rims of the cylinder.
    """
    base = (172, 176, 182)
    f = 0.74
    f += 0.34 * gauss(u, 0.30, 0.17)
    f += 0.10 * gauss(u, 0.55, 0.30)
    f -= 0.16 * gauss(u, 0.97, 0.10)
    f -= 0.10 * gauss(u, 0.02, 0.05)
    return tuple(min(255, int(c * f)) for c in base)


def draw_kettle_body(img):
    sil = kettle_silhouette()
    mask = Image.new("L", (CW, CH), 0)
    md = ImageDraw.Draw(mask)
    md.polygon(sil, fill=255)

    # cylindrical shading: one horizontal gradient strip, stretched tall
    left, right = KCX - 176, KCX + 176
    strip = Image.new("RGB", (int((right - left) * S), 1))
    sd = ImageDraw.Draw(strip)
    for i in range(strip.width):
        u = i / (strip.width - 1)
        sd.point((i, 0), fill=steel_column(u))
    strip = strip.resize((strip.width, CH))
    img.paste(strip, (int(left * S), 0), mask.crop((int(left * S), 0, int(right * S), CH)))

    # vertical fall-off: a breath of shade toward the base, sheen at shoulder
    shade = Image.new("L", (CW, CH), 0)
    shd = ImageDraw.Draw(shade)
    for j in range(CH):
        t = j / CH
        a = int(46 * smoothstep((t - (KTOP - 40) / H) / ((KBOT - KTOP + 40) / H)) ** 1.5)
        shd.line([(0, j), (CW, j)], fill=max(0, min(60, a)))
    black = Image.new("RGB", (CW, CH), (52, 54, 58))
    img = Image.composite(black, img, Image.composite(shade, Image.new("L", (CW, CH), 0), mask))

    # brushing: fine horizontal streaks
    brush = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    bd = ImageDraw.Draw(brush)
    for _ in range(1100):
        y = rng.uniform(KTOP + 6, KBOT - 8)
        hw = kettle_halfwidth((KBOT - y) / (KBOT - KTOP)) - 4
        x0 = KCX - hw + rng.uniform(0, hw * 0.7)
        ln = rng.uniform(30, hw * 1.1)
        if rng.random() < 0.5:
            col = (255, 255, 255, rng.randint(3, 9))
        else:
            col = (30, 32, 36, rng.randint(3, 8))
        bd.line([pt(x0, y), pt(min(x0 + ln, KCX + hw), y)], fill=col, width=max(1, S // 2))
    img = Image.alpha_composite(img.convert("RGBA"), brush).convert("RGB")

    # specular kiss on the upper-left shoulder
    spec = Image.new("L", (CW, CH), 0)
    spd = ImageDraw.Draw(spec)
    spd.ellipse(box(KCX - 150, KTOP + 26, KCX - 30, KTOP + 190), fill=64)
    spec = spec.filter(ImageFilter.GaussianBlur(26 * S // 2))
    spec = Image.composite(spec, Image.new("L", (CW, CH), 0), mask)
    img = Image.composite(Image.new("RGB", (CW, CH), (255, 255, 255)), img, spec)

    # crisp manufactured edge
    d = ImageDraw.Draw(img, "RGBA")
    d.line(sil + [sil[0]], fill=(70, 73, 78, 110), width=max(1, S))
    return img


def draw_base_band(img):
    d = ImageDraw.Draw(img, "RGBA")
    y0, y1 = KBOT - 48, KBOT
    # charcoal band, shaded with the same cylinder light as the body so
    # it wraps instead of reading as a separate black box
    sil = kettle_silhouette()
    mask = Image.new("L", (CW, CH), 0)
    md = ImageDraw.Draw(mask)
    md.polygon(sil, fill=255)
    md.rectangle([0, 0, CW, int(y0 * S)], fill=0)
    left, right = KCX - 176, KCX + 176
    strip = Image.new("RGB", (int((right - left) * S), 1))
    sd = ImageDraw.Draw(strip)
    for i in range(strip.width):
        u = i / (strip.width - 1)
        c = steel_column(u)
        sd.point((i, 0), fill=tuple(int(v * 0.30) for v in c))
    strip = strip.resize((strip.width, CH))
    img.paste(strip, (int(left * S), 0), mask.crop((int(left * S), 0, int(right * S), CH)))
    # steel trim line above the band
    hw = kettle_halfwidth((KBOT - y0) / (KBOT - KTOP))
    d.line([pt(KCX - hw, y0), pt(KCX + hw, y0)], fill=(210, 214, 219, 200), width=max(1, S))
    d.line([pt(KCX - hw, y0 + 2.5), pt(KCX + hw, y0 + 2.5)], fill=(40, 42, 46, 160), width=max(1, S))
    # amber power light, lit
    glow = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(box(492, 756, 524, 788), fill=(255, 166, 48, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(9 * S // 2))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)
    d.ellipse(box(502, 766, 514, 778), fill=(255, 176, 66))
    d.ellipse(box(505, 769, 510, 774), fill=(255, 224, 160))
    return img


def _bez(p0, p1, p2, p3, t):
    mt = 1 - t
    return (
        mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1],
    )


def draw_spout(img):
    """Tapered spout sweeping up the left flank; tip at (214, 458).

    One smooth cubic centreline, shaded like a bent steel tube: bright
    along the top edge, falling to shade underneath, with a soft welded
    seam where it leaves the body.
    """
    centre = [_bez((362, 702), (238, 632), (204, 536), (214, 458), i / 60)
              for i in range(61)]

    def width_at(t):
        return lerp(56, 22, smoothstep(t)) / 2

    left_edge, right_edge = [], []
    for i, (x, y) in enumerate(centre):
        t = i / 60
        if i < 60:
            nx, ny = centre[i + 1]
        else:
            nx, ny = 2 * x - centre[i - 1][0], 2 * y - centre[i - 1][1]
        dx, dy = nx - x, ny - y
        ln = math.hypot(dx, dy) or 1
        px, py = -dy / ln, dx / ln
        wdt = width_at(t)
        left_edge.append((x + px * wdt, y + py * wdt))
        right_edge.append((x - px * wdt, y - py * wdt))
    poly = [pt(x, y) for x, y in left_edge + right_edge[::-1]]

    mask = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)

    # steel tube shading: a function of height, lit from the upper left
    grad = Image.new("RGB", (CW, CH), (0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for j in range(CH):
        yy = j / S
        c = mix((104, 108, 114), (202, 206, 212), clamp((700 - yy) / 280))
        gd.line([(0, j), (CW, j)], fill=c)
    img.paste(grad, (0, 0), mask)

    clear = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    # roundness: a bright core running along the centreline
    core = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(core).line([pt(x, y) for x, y in centre],
                              fill=(255, 255, 255, 105), width=int(9 * S), joint="curve")
    core = core.filter(ImageFilter.GaussianBlur(5 * S // 2))
    img = Image.alpha_composite(img.convert("RGBA"),
                                Image.composite(core, clear, mask)).convert("RGB")
    # shade along the underside
    under = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(under).line([pt(x, y) for x, y in right_edge],
                               fill=(38, 40, 44, 120), width=int(11 * S), joint="curve")
    under = under.filter(ImageFilter.GaussianBlur(6 * S // 2))
    img = Image.alpha_composite(img.convert("RGBA"),
                                Image.composite(under, clear, mask)).convert("RGB")
    # light along the top edge
    top = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(top).line([pt(x, y) for x, y in left_edge],
                             fill=(255, 255, 255, 120), width=int(5 * S), joint="curve")
    top = top.filter(ImageFilter.GaussianBlur(4 * S // 2))
    img = Image.alpha_composite(img.convert("RGBA"),
                                Image.composite(top, clear, mask)).convert("RGB")

    d = ImageDraw.Draw(img, "RGBA")
    # tip opening
    d.ellipse(box(200, 449, 230, 467), fill=(40, 42, 46))
    d.ellipse(box(203.5, 452, 226.5, 464), fill=(14, 15, 18))
    return img


def draw_weld(img):
    """Soft shadow pooled where the spout dives into the body."""
    weld = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(weld).ellipse(box(244, 606, 322, 700), fill=(30, 32, 36, 68))
    weld = weld.filter(ImageFilter.GaussianBlur(11 * S // 2))
    return Image.alpha_composite(img.convert("RGBA"), weld).convert("RGB")

def draw_handle(img):
    d = ImageDraw.Draw(img, "RGBA")
    # matte black C-handle on the right flank, slim as a real jug grip
    path = []
    p0, p1, p2, p3 = (588, 482), (700, 506), (704, 616), (586, 672)
    for i in range(41):
        t = i / 40
        path.append(pt(*_bez(p0, p1, p2, p3, t)))
    d.line(path, fill=(24, 24, 27), width=int(21 * S), joint="curve")
    for p in (path[0], path[-1]):
        d.ellipse([p[0] - 10 * S, p[1] - 10 * S, p[0] + 10 * S, p[1] + 10 * S], fill=(24, 24, 27))
    # mounts, tucked close to the body
    d.rounded_rectangle(box(576, 468, 604, 498), radius=5 * S, fill=(30, 30, 33))
    d.rounded_rectangle(box(574, 658, 602, 688), radius=5 * S, fill=(30, 30, 33))
    # one soft sheen along the top of the grip
    sheen = [pt(x, y - 7) for x, y in
             [_bez(p0, p1, p2, p3, t) for t in [i / 40 for i in range(6, 22)]]]
    d.line(sheen, fill=(150, 152, 158, 80), width=int(4 * S), joint="curve")
    return img


def draw_rim_and_water(img):
    d = ImageDraw.Draw(img)
    # rim ring
    d.ellipse(box(KCX - 104, KTOP - 23, KCX + 104, KTOP + 23), fill=(198, 202, 208))
    d.ellipse(box(KCX - 104, KTOP - 23, KCX + 104, KTOP + 23), outline=(120, 124, 130), width=max(1, S))
    # dark throat
    d.ellipse(box(KCX - 90, KTOP - 17, KCX + 90, KTOP + 17), fill=(24, 26, 30))
    # water surface inside
    d.ellipse(box(KCX - 84, KTOP - 14, KCX + 84, KTOP + 14), fill=(86, 118, 138))
    d.ellipse(box(KCX - 84, KTOP - 14, KCX + 84, KTOP - 2), fill=(120, 152, 172))
    # quiet ripples
    dr = ImageDraw.Draw(img, "RGBA")
    for r, a in ((58, 70), (40, 90), (24, 110)):
        dr.arc(box(KCX - r, KTOP - r * 0.17, KCX + r, KTOP + r * 0.17),
               start=15, end=165, fill=(214, 232, 240, a), width=max(1, S))
    return img


def draw_gauge(img):
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = 556, 556, 586, 700
    d.rounded_rectangle(box(x0 - 4, y0 - 4, x1 + 4, y1 + 4), radius=10 * S, fill=(52, 54, 58, 255))
    d.rounded_rectangle(box(x0, y0, x1, y1), radius=8 * S, fill=(206, 216, 222, 255))
    # water level at 62%
    lvl = y1 - (y1 - y0) * 0.62
    d.rounded_rectangle(box(x0, lvl, x1, y1), radius=8 * S, fill=(64, 116, 164, 255))
    d.rectangle(box(x0, lvl, x1, lvl + 10), fill=(64, 116, 164, 255))
    d.line([pt(x0 + 2, lvl), pt(x1 - 2, lvl)], fill=(168, 208, 232, 255), width=max(1, S))
    # ticks
    for i in range(5):
        yy = y0 + 14 + i * (y1 - y0 - 28) / 4
        ln = 9 if i % 2 == 0 else 6
        d.line([pt(x0 + 3, yy), pt(x0 + 3 + ln, yy)], fill=(40, 44, 48, 220), width=max(1, S))
    # glass sheen
    d.polygon([pt(x0 + 5, y1 - 8), pt(x0 + 15, y0 + 8), pt(x0 + 23, y0 + 8), pt(x0 + 13, y1 - 8)],
              fill=(255, 255, 255, 46))
    return img


def draw_plate(img):
    d = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = KCX - 106, 602, KCX + 94, 670
    # recessed plate: light lip below, dark lip above, brushed face
    d.rounded_rectangle(box(x0, y0 + 2, x1, y1 + 2), radius=8 * S, fill=(228, 231, 235, 160))
    d.rounded_rectangle(box(x0, y0, x1, y1), radius=8 * S, fill=(148, 152, 158, 255))
    d.rounded_rectangle(box(x0 + 3, y0 + 3, x1 - 3, y1 - 3), radius=6 * S, outline=(96, 100, 106, 200), width=max(1, S))
    for i in range(26):
        y = y0 + 4 + i * (y1 - y0 - 8) / 26
        d.line([pt(x0 + 6, y), pt(x1 - 6, y)], fill=(255, 255, 255, rng.randint(4, 10)))
    # engraved lettering: pale shadow pass, then dark cut
    f1 = get_font(21, bold=True)
    f2 = get_font(13.5, bold=False)
    pcx = (x0 + x1) / 2
    for dy, col in ((1.2, (226, 229, 233, 255)), (0, (44, 46, 50, 255))):
        draw_tracked(d, pcx, y0 + 10 + dy, "PERPETUA · K-1", f1, col, 2.4 * S)
    for dy, col in ((1.0, (226, 229, 233, 255)), (0, (52, 54, 58, 255))):
        draw_tracked(d, pcx, y0 + 42 + dy, "SELF-REFILLING · 1.7 L", f2, col, 2.0 * S)
    # four tiny screws, one in each corner
    for sx, sy in ((x0 + 9, y0 + 9), (x1 - 9, y0 + 9), (x0 + 9, y1 - 9), (x1 - 9, y1 - 9)):
        d.ellipse(box(sx - 2.6, sy - 2.6, sx + 2.6, sy + 2.6), fill=(96, 99, 104, 255))
        d.line([pt(sx - 1.8, sy), pt(sx + 1.8, sy)], fill=(210, 213, 217, 200), width=max(1, S))
    return img


# ---------------------------------------------------------------- the impossible stream

def stream_point(t):
    p0, p1, p2, p3 = (216, 448), (238, 292), (356, 262), (458, 428)
    mt = 1 - t
    return (
        mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
        mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1],
    )


def stream_radius(t):
    # thick at the spout, stretched thin over the crown, gathering as it falls
    return 5.2 + 7.6 * (1 - t) ** 2.2 + 3.2 * t ** 3


def draw_stream(img):
    layer = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = 260
    pts = [stream_point(i / n) for i in range(n + 1)]
    for scale, col in ((2.1, (150, 196, 226, 66)), (1.35, (178, 216, 240, 120)),
                       (0.66, (244, 252, 254, 242))):
        for (x, y), t in zip(pts, [i / n for i in range(n + 1)]):
            r = stream_radius(t) * scale
            d.ellipse(box(x - r, y - r, x + r, y + r), fill=col)
    # droplets shaken off the arc
    for _ in range(210):
        t = rng.random()
        x, y = stream_point(t)
        spread = stream_radius(t) + rng.uniform(2, 16)
        ang = rng.uniform(0, math.tau)
        dx, dy = math.cos(ang) * spread, math.sin(ang) * spread * 0.8 + rng.uniform(0, 10)
        r = rng.uniform(0.8, 3.0)
        a = rng.randint(110, 225)
        d.ellipse(box(x + dx - r, y + dy - r, x + dx + r, y + dy + r),
                  fill=(232, 244, 250, a))
    img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

    # splash where the stream lands back home
    d = ImageDraw.Draw(img, "RGBA")
    lx, ly = 458, 430
    for i in range(16):
        ang = rng.uniform(-math.pi * 0.88, -math.pi * 0.12)
        ln = rng.uniform(7, 22)
        x2, y2 = lx + math.cos(ang) * ln, ly + math.sin(ang) * ln * 0.6
        d.line([pt(lx, ly), pt(x2, y2)], fill=(226, 242, 248, 190), width=max(1, S))
        d.ellipse(box(x2 - 1.6, y2 - 1.6, x2 + 1.6, y2 + 1.6), fill=(236, 248, 252, 210))
    for r, a in ((16, 150), (26, 90)):
        d.arc(box(lx - r, ly - r * 0.18, lx + r, ly + r * 0.18), start=10, end=170,
              fill=(220, 238, 246, a), width=max(1, S))
    return img


# ---------------------------------------------------------------- the one accessory

def draw_mug(img):
    mcx, mtop, mbot = 792, 648, 788
    # silhouette
    def hw(t):  # 0 top, 1 bottom
        return lerp(79, 66, smoothstep(t)) + 3 * math.sin(t * math.pi)
    pts = []
    n = 40
    for i in range(n + 1):
        t = i / n
        pts.append(pt(mcx - hw(t), lerp(mtop, mbot, t)))
    for i in range(n, -1, -1):
        t = i / n
        pts.append(pt(mcx + hw(t), lerp(mtop, mbot, t)))
    mask = Image.new("L", (CW, CH), 0)
    md = ImageDraw.Draw(mask)
    md.polygon(pts, fill=255)
    # ceramic shading: near-white, lit from upper left
    grad = Image.new("RGB", (CW, CH), (0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(CW):
        u = i / CW
        c = mix((240, 241, 242), (188, 191, 196),
                clamp((u - (mcx - 95) / W) / (200 / W)))
        gd.line([(i, 0), (i, CH)], fill=c)
    img.paste(grad, (0, 0), mask)
    # settle the mug: gentle shade gathering toward its base
    shade = Image.new("L", (CW, CH), 0)
    shd = ImageDraw.Draw(shade)
    for j in range(int(mtop * S), CH):
        a = int(52 * smoothstep((j / S - mtop) / (mbot - mtop)) ** 1.4)
        shd.line([(0, j), (CW, j)], fill=a)
    img = Image.composite(Image.new("RGB", (CW, CH), (120, 122, 126)), img,
                          Image.composite(shade, Image.new("L", (CW, CH), 0), mask))
    # glossy streak, softened so it reads as glaze light, not a sticker
    streak = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    ImageDraw.Draw(streak).polygon(
        [pt(mcx - 58, mtop + 30), pt(mcx - 18, mtop + 24),
         pt(mcx - 8, mbot - 58), pt(mcx - 44, mbot - 52)],
        fill=(255, 255, 255, 36))
    streak = streak.filter(ImageFilter.GaussianBlur(8 * S // 2))
    img = Image.alpha_composite(img.convert("RGBA"),
                                Image.composite(streak, Image.new("RGBA", (CW, CH), (0, 0, 0, 0)), mask)).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    # handle: soft grey under-stroke, then ceramic white
    hp = []
    p0, p1, p2, p3 = (862, 676), (928, 690), (928, 742), (858, 756)
    for i in range(31):
        t = i / 30
        mt = 1 - t
        hp.append(pt(mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                     mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))
    d.line(hp, fill=(172, 175, 179), width=int(17 * S), joint="curve")
    d.line(hp, fill=(240, 241, 242), width=int(12 * S), joint="curve")
    # rim and the empty inside: near wall lit, far wall in soft shade,
    # and the dry inside bottom showing as a smaller, lighter ellipse
    d.ellipse(box(mcx - 79, mtop - 15, mcx + 79, mtop + 15), fill=(243, 244, 245))
    d.ellipse(box(mcx - 79, mtop - 15, mcx + 79, mtop + 15), outline=(170, 173, 177), width=max(1, S))
    d.ellipse(box(mcx - 67, mtop - 11, mcx + 67, mtop + 11), fill=(176, 179, 183))
    d.ellipse(box(mcx - 67, mtop - 11, mcx + 30, mtop + 11), fill=(198, 201, 205))
    d.ellipse(box(mcx - 44, mtop - 4, mcx + 44, mtop + 9), fill=(206, 208, 211))
    d.ellipse(box(mcx - 44, mtop - 4, mcx + 44, mtop + 9), outline=(168, 171, 175), width=max(1, S))
    return img


# ---------------------------------------------------------------- assemble

def main():
    img = make_background()
    # shadows: cast (offset down-right of the upper-left key) + contact
    img = soft_shadow(img, KCX + 26, FLOOR + 8, 215, 26, 46, 26, dx=18, dy=4)
    img = soft_shadow(img, KCX, FLOOR + 4, 185, 17, 105, 12)
    img = soft_shadow(img, 792 + 12, FLOOR + 6, 108, 15, 92, 10)

    img = draw_spout(img)          # root dives behind the body's flank
    img = draw_kettle_body(img)
    img = draw_weld(img)
    img = draw_base_band(img)
    img = draw_handle(img)
    img = draw_rim_and_water(img)
    img = draw_gauge(img)
    img = draw_plate(img)
    img = draw_mug(img)
    img = draw_stream(img)         # the impossible part, on top of all

    # photographic grain
    noise = Image.frombytes("L", (W, H), rng.randbytes(W * H))
    noise = noise.resize((CW, CH)).filter(ImageFilter.GaussianBlur(0.6))
    img = Image.composite(
        Image.new("RGB", (CW, CH), (255, 255, 255)), img,
        noise.point(lambda v: int(abs(v - 128) * 0.10)))
    img = Image.composite(
        Image.new("RGB", (CW, CH), (0, 0, 0)), img,
        noise.point(lambda v: int(max(0, (128 - v)) * 0.06)))

    img = img.resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, optimize=True)
    print("wrote", OUT, img.size, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
