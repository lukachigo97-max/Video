#!/usr/bin/env python3
"""NAMICA thread-lift explainer reel (1080x1920, 30 fps, 45 s, silent, EN + KA text).

Usage:
  python3 build.py output/NAMICA_reel_v1.mp4      # full render
  python3 build.py --stills DIR 1.0 7.5 20 ...     # PNG previews at the given seconds

All patient coordinates below are pixel positions in the EXIF-rotated photos
(1512x2016) in assets/, measured by hand.
"""
import math
import os
import subprocess
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
W, H, FPS, DUR = 1080, 1920, 30, 45.0

# ------------------------------------------------------------------ presenter
PRESENTER_NAME = "Luka Chigogidze"
PRESENTER_IG = "@your_instagram"          # <- replace with the real handle

# ------------------------------------------------------------------ style
PURPLE = (124, 84, 214)
PURPLE_D = (52, 28, 104)
LAV = (222, 210, 255)
WHITE = (255, 255, 255)
GOLD = (255, 206, 84)

F_BLACK = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
F_KA_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_KA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


@lru_cache(None)
def font(path, size):
    return ImageFont.truetype(path, size)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def seg(t, a, b):
    return clamp((t - a) / (b - a))


def lerp(a, b, k):
    return a + (b - a) * k


# ------------------------------------------------------------------ photos
# eye = near-eye iris, nose = tip, chin = soft-tissue pogonion; eyes = blur ellipses (x, y, rx, ry)
PHOTOS = {
    "b_lobl": dict(eye=(725, 838), nose=(400, 1050), chin=(470, 1500), left=True,
                   eyes=[(728, 842, 80, 48), (478, 832, 58, 42)]),
    "a_lobl": dict(eye=(714, 824), nose=(421, 1014), chin=(464, 1478), left=True,
                   eyes=[(714, 826, 80, 48), (505, 828, 58, 42)]),
    "b_lprof": dict(eye=(638, 819), nose=(357, 1014), chin=(452, 1467), left=True,
                    eyes=[(642, 822, 70, 48)]),
    "a_lprof": dict(eye=(762, 852), nose=(460, 1014), chin=(548, 1478), left=True,
                    eyes=[(762, 850, 70, 48)]),
    "b_robl": dict(eye=(714, 824), nose=(1024, 1050), chin=(917, 1467), left=False,
                   eyes=[(714, 826, 80, 48), (938, 830, 54, 42)]),
    "a_robl": dict(eye=(650, 883), nose=(1043, 1121), chin=(948, 1550), left=False,
                   eyes=[(650, 885, 84, 50), (926, 885, 64, 46)]),
    "b_rprof": dict(eye=(757, 867), nose=(1029, 1057), chin=(917, 1443), left=False,
                    eyes=[(757, 868, 70, 48)]),
    "a_rprof": dict(eye=(757, 812), nose=(1062, 990), chin=(990, 1419), left=False,
                    eyes=[(757, 814, 70, 48)]),
}
ORDER = ["lprof", "lobl", "robl", "rprof"]   # turn of the head, left to right


def blur_eyes(im, eyes):
    out = im.copy()
    for x, y, rx, ry in eyes:
        pad = int(rx * 1.7)
        box = (x - pad, y - pad, x + pad, y + pad)
        crop = out.crop(box)
        bl = crop.filter(ImageFilter.GaussianBlur(rx * 0.33))
        m = Image.new("L", crop.size, 0)
        ImageDraw.Draw(m).ellipse((pad - rx, pad - ry, pad + rx, pad + ry), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(rx * 0.16))
        out.paste(Image.composite(bl, crop, m), box[:2])
    return out


IMG = {}
for _k, _p in PHOTOS.items():
    IMG[_k] = blur_eyes(Image.open(os.path.join(ASSETS, _k + ".jpg")).convert("RGB"), _p["eyes"])


def sim_fit(src, dst):
    """Least-squares similarity dst = [[a,-b],[b,a]] src + t."""
    A, B = [], []
    for (x, y), (u, v) in zip(src, dst):
        A += [[x, -y, 1, 0], [y, x, 0, 1]]
        B += [u, v]
    return tuple(np.linalg.lstsq(np.array(A, float), np.array(B, float), rcond=None)[0])


def pts(name):
    p = PHOTOS[name]
    return [p["eye"], p["nose"], p["chin"]]


# maps before-photo coords -> after-photo coords, per angle
ALIGN = {k: sim_fit(pts("b_" + k), pts("a_" + k)) for k in ORDER}


def view(img, cx, cy, s, size=(W, H), M=None):
    """Render img so source point (cx, cy) lands mid-frame; s = source px per output px."""
    w, h = size
    ox, oy = cx - s * w / 2, cy - s * h / 2
    if M is None:
        c = (s, 0, ox, 0, s, oy)
    else:
        a, b, tx, ty = M
        c = (a * s, -b * s, a * ox - b * oy + tx, b * s, a * s, b * ox + a * oy + ty)
    return img.transform(size, Image.Transform.AFFINE, c,
                         resample=Image.Resampling.BICUBIC, fillcolor=(10, 10, 12))


def to_out(p, cam, size=(W, H)):
    cx, cy, s = cam
    return ((p[0] - cx) / s + size[0] / 2, (p[1] - cy) / s + size[1] / 2)


def photo_cam(name, zoom=1.0):
    p = PHOTOS[name]
    s = (p["chin"][1] - p["eye"][1]) / 700 / zoom
    cy = p["eye"][1] + 130 * s
    cx = p["nose"][0] + (430 * s if p["left"] else -430 * s)
    return cx, cy, s


def cam_lerp(c0, c1, k):
    return (lerp(c0[0], c1[0], k), lerp(c0[1], c1[1], k),
            math.exp(lerp(math.log(c0[2]), math.log(c1[2]), k)))


# ------------------------------------------------------------------ drawing helpers
def paste(dst, src, x, y, a=1.0):
    """Alpha-composite src onto RGBA dst at (x, y), clipped to bounds, with opacity a."""
    if a <= 0.003:
        return
    x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    s = src.crop((sx0, sy0, sx1, sy1))
    if a < 0.997:
        s = s.copy()
        s.putalpha(s.getchannel("A").point(lambda v: int(v * a)))
    dst.alpha_composite(s, (x + sx0, y + sy0))


def wrap(text, fnt, maxw):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@lru_cache(None)
def block(spec, maxw=960, align="c"):
    """spec: tuple of (text, font_path, size, fg, bg_rgba_or_None, padx, pady, gap).
    Every wrapped line gets its own highlight box (reel-caption style)."""
    rows = []
    for text, fp, size, fg, bg, padx, pady, gap in spec:
        f = font(fp, size)
        lines = wrap(text, f, maxw - 2 * padx)
        for i, ln in enumerate(lines):
            d = ImageDraw.Draw(Image.new("L", (1, 1)))
            tw = d.textlength(ln, font=f)
            asc, desc = f.getmetrics()
            rows.append((ln, f, fg, bg, padx, pady, tw, asc + desc,
                         gap if i == len(lines) - 1 else 4))
    bw = int(max(r[6] + 2 * r[4] for r in rows)) + 2
    bh = int(sum(r[7] + 2 * r[5] + r[8] for r in rows)) + 2
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = 0
    for ln, f, fg, bg, padx, pady, tw, lh, gap in rows:
        boxw = tw + 2 * padx
        x = (bw - boxw) / 2 if align == "c" else (0 if align == "l" else bw - boxw)
        if bg:
            d.rounded_rectangle((x, y, x + boxw, y + lh + 2 * pady), radius=10, fill=bg)
        d.text((x + padx, y + pady), ln, font=f, fill=fg)
        y += lh + 2 * pady + gap
    return im


def cap(en, ka, en_size=46, ka_size=33, en_bg=PURPLE + (240,), ka_bg=(16, 8, 34, 190), maxw=960):
    return block(((en, F_BOLD, en_size, WHITE, en_bg, 22, 10, 8),
                  (ka, F_KA_B, ka_size, WHITE, ka_bg, 18, 9, 0)), maxw)


def title(en, ka, en_size=84, ka_size=42):
    return block(((en, F_BLACK, en_size, WHITE, PURPLE + (245,), 28, 10, 10),
                  (ka, F_KA_B, ka_size, WHITE, PURPLE_D + (225,), 20, 10, 0)), 1000)


def put_center(dst, im, y, a=1.0, rise=0.0):
    paste(dst, im, (W - im.width) / 2, y + (1 - a) * rise, a)


@lru_cache(None)
def tag(en, ka, color=PURPLE):
    return block(((en + "  ·  " + ka, F_KA_B, 34, WHITE, color + (240,), 22, 12, 0),), 900)


def glow_line(layer, P, width, color, glow=8, glow_a=150):
    g = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(g).line(P, fill=color[:3] + (glow_a,), width=width + glow, joint="curve")
    g = g.filter(ImageFilter.GaussianBlur(glow))
    layer.alpha_composite(g)
    ImageDraw.Draw(layer).line(P, fill=color, width=width, joint="curve")


def dashed(d, P, color, width=3, dash=16, gap=10):
    for (x0, y0), (x1, y1) in zip(P[:-1], P[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = 0.0
        while n < L:
            e = min(L, n + dash)
            d.line([(x0 + (x1 - x0) * n / L, y0 + (y1 - y0) * n / L),
                    (x0 + (x1 - x0) * e / L, y0 + (y1 - y0) * e / L)], fill=color, width=width)
            n += dash + gap


def catmull(points, closed=False, n=10):
    P = [np.array(p, float) for p in points]
    if closed:
        P = [P[-1]] + P + [P[0], P[1]]
    else:
        P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(P[-2])
    return np.array(out)


def chevron(d, x, y, size, up, color, width=6):
    s = -1 if up else 1
    d.line([(x - size, y - s * size * 0.55), (x, y + s * size * 0.45), (x + size, y - s * size * 0.55)],
           fill=color, width=width, joint="curve")


# ------------------------------------------------------------------ presenter badge
def circle_photo(diam):
    im = Image.open(os.path.join(ASSETS, "presenter.jpg")).convert("RGB")
    cx, cy, r = 700, 560, 400
    im = im.crop((cx - r, cy - r, cx + r, cy + r)).resize((diam * 2, diam * 2), Image.Resampling.LANCZOS)
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, im.width - 1, im.height - 1), fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, 0), m)
    return out.resize((diam, diam), Image.Resampling.LANCZOS)


@lru_cache(None)
def badge(diam=150, name_size=34, ig_size=28):
    ph = circle_photo(diam)
    ring = 5
    fn, fi = font(F_BOLD, name_size), font(F_MED, ig_size)
    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    tw = int(max(d0.textlength(PRESENTER_NAME, font=fn), d0.textlength(PRESENTER_IG, font=fi)))
    bw = diam + 2 * ring + 26 + tw + 30
    bh = diam + 2 * ring
    im = Image.new("RGBA", (bw + 20, bh + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    py0 = 10 + bh / 2 - (name_size + ig_size + 26) / 2 - 8
    d.rounded_rectangle((10 + bh / 2, py0, 10 + bw, py0 + name_size + ig_size + 42),
                        radius=(name_size + ig_size + 42) / 2, fill=(14, 8, 30, 200))
    d.ellipse((10, 10, 10 + bh, 10 + bh), fill=WHITE)
    d.ellipse((10 + ring - 2, 10 + ring - 2, 10 + bh - ring + 2, 10 + bh - ring + 2), fill=PURPLE)
    im.alpha_composite(ph, (10 + ring, 10 + ring))
    tx = 10 + bh + 22
    d.text((tx, py0 + 10), PRESENTER_NAME, font=fn, fill=WHITE)
    d.text((tx, py0 + 18 + name_size), PRESENTER_IG, font=fi, fill=LAV)
    return im


# ------------------------------------------------------------------ fat compartments (on b_lobl)
TEX_O = (260, 260)


def make_fat_texture(w=1200, h=1500, seed=7):
    rng = np.random.default_rng(seed)
    tex = Image.new("RGBA", (w, h), (226, 176, 44, 255))
    sprites = []
    for r in (5, 7, 9, 11, 14):
        n = 2 * r + 3
        yy, xx = np.mgrid[0:n, 0:n].astype(float)
        c = n / 2 - 0.5
        dist = np.hypot(xx - c, yy - c) / r
        hl = np.hypot(xx - c + 0.35 * r, yy - c + 0.35 * r) / (1.3 * r)
        k = np.clip(hl, 0, 1)[..., None]
        col = np.array([255, 234, 140]) * (1 - k) + np.array([206, 150, 30]) * k
        a = np.clip((1 - dist) * r * 0.9, 0, 1) * 255
        sprites.append(Image.fromarray(np.dstack([col, a]).astype(np.uint8), "RGBA"))
    for _ in range(int(w * h / 150)):
        sp = sprites[rng.integers(0, len(sprites))]
        tex.alpha_composite(sp, (int(rng.integers(-10, w)), int(rng.integers(-10, h))))
    return tex


FAT_TEX = make_fat_texture()

# name, outline points, aging shift (dx, dy), aging scale (sx, sy)
COMPS = [
    ("central forehead", [(470, 470), (560, 445), (600, 520), (592, 650), (545, 700), (482, 668), (456, 560)], (0, 10), (1, .98)),
    ("middle forehead", [(625, 445), (780, 425), (900, 470), (935, 560), (885, 675), (765, 668), (645, 662), (612, 560)], (0, 14), (1, .97)),
    ("lateral temporal-cheek", [(952, 480), (1040, 520), (1082, 640), (1110, 800), (1122, 980), (1112, 1150), (1092, 1280), (1045, 1330), (1004, 1250), (992, 1080), (982, 900), (944, 762), (928, 600)], (0, 24), (.97, 1.03)),
    ("superior orbital", [(652, 748), (760, 732), (860, 760), (874, 800), (800, 792), (720, 793), (662, 798)], (0, 16), (1, .9)),
    ("inferior orbital", [(672, 892), (760, 886), (812, 900), (792, 937), (720, 947), (672, 932)], (0, 22), (.95, .85)),
    ("lateral orbital", [(832, 800), (902, 790), (942, 850), (932, 932), (872, 952), (832, 900)], (-2, 22), (.94, .92)),
    ("medial cheek", [(612, 952), (702, 946), (782, 976), (800, 1060), (762, 1130), (682, 1122), (622, 1060)], (-6, 58), (.9, .92)),
    ("middle cheek", [(812, 982), (902, 962), (962, 1042), (972, 1200), (932, 1282), (862, 1262), (822, 1152), (802, 1062)], (-6, 46), (.94, .97)),
    ("nasolabial", [(577, 1102), (622, 1096), (662, 1152), (682, 1240), (662, 1282), (632, 1252), (592, 1182)], (-8, 40), (1.12, 1.03)),
    ("superior jowl", [(692, 1292), (762, 1282), (822, 1322), (822, 1392), (762, 1412), (702, 1382), (672, 1332)], (0, 50), (1.06, 1.05)),
    ("inferior jowl", [(642, 1412), (742, 1422), (812, 1442), (802, 1508), (722, 1528), (642, 1500), (612, 1452)], (0, 52), (1.1, 1.06)),
    ("submandibular", [(832, 1422), (932, 1382), (1010, 1352), (1030, 1402), (962, 1462), (862, 1492)], (0, 44), (1.06, 1.05)),
]
for i, c in enumerate(COMPS):
    sm = catmull(c[1], closed=True, n=8)
    COMPS[i] = dict(name=c[0], smooth=sm, cen=sm.mean(0), d=np.array(c[2], float), s=np.array(c[3], float))

# label groups: EN, KA, anchor compartment, label y (output px, anatomy camera)
LABELS = [
    ("Forehead fat", "შუბლის ცხიმი", 1, 500),
    ("Lateral temporal-cheek fat", "საფეთქელ-ლოყის ლატ. ცხიმი", 2, 650),
    ("Orbital fat", "ორბიტული ცხიმი", 5, 800),
    ("Middle cheek fat", "ლოყის შუა ცხიმი", 7, 960),
    ("Medial cheek fat", "ლოყის მედიალური ცხიმი", 6, 1110),
    ("Nasolabial fat", "ნაზოლაბიური ცხიმი", 8, 1260),
    ("Jowl fat", "ბრილების ცხიმი", 10, 1410),
]


@lru_cache(None)
def label_img(en, ka):
    return block(((en, F_BOLD, 25, (30, 20, 50), (255, 255, 255, 236), 14, 6, 0),
                  (ka, F_KA, 20, (60, 40, 100), (255, 255, 255, 236), 14, 5, 0)), 400, align="r")


def comp_state(c, age, lift):
    """age 0..1 descends; lift 0..1 brings it back (slightly above youthful position)."""
    k = age - 1.08 * lift * age
    off = c["d"] * k
    sc = 1 + (c["s"] - 1) * max(k, 0)
    return off, sc


def comp_sprite(c, off, sc, alpha, glow=0.0):
    P = c["cen"] + (c["smooth"] - c["cen"]) * sc + off
    x0, y0 = np.floor(P.min(0)) - 8
    x1, y1 = np.ceil(P.max(0)) + 8
    bw, bh = int(x1 - x0), int(y1 - y0)
    m = Image.new("L", (bw * 2, bh * 2), 0)
    ImageDraw.Draw(m).polygon([tuple((p - [x0, y0]) * 2) for p in P], fill=255)
    m = m.resize((bw, bh), Image.Resampling.LANCZOS)
    tx, ty = int(x0 - off[0] - TEX_O[0]), int(y0 - off[1] - TEX_O[1])
    tex = np.asarray(FAT_TEX.crop((tx, ty, tx + bw, ty + bh)), float)[..., :3]
    ma = np.asarray(m, float) / 255
    shade = np.asarray(m.filter(ImageFilter.GaussianBlur(8)), float)[..., None] / 255
    edge = np.asarray(ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(5))), float)[..., None] / 255
    col = tex * (0.6 + 0.4 * shade)
    col = col * (1 - edge * 0.85) + np.array([150, 96, 10]) * edge * 0.85
    col = np.clip(col + glow * 60, 0, 255)
    a = np.clip(ma * alpha * 0.56 + edge[..., 0] * alpha * 0.35, 0, 1) * 255
    return Image.fromarray(np.dstack([col, a]).astype(np.uint8), "RGBA"), (int(x0), int(y0))


ANAT_CAM = (850, 980, 1.0)
BASE_LOBL = IMG["b_lobl"].convert("RGBA")


def anatomy_frame(cam, age, lift, alphas, glow=0.0, photo=None):
    base = (photo or BASE_LOBL).copy()
    for c, a in zip(COMPS, alphas):
        if a <= 0.01:
            continue
        off, sc = comp_state(c, age, lift)
        pop = 0.9 + 0.1 * ease_out(a) if a < 1 else 1.0
        sp, xy = comp_sprite(c, off, sc * pop, min(a, 1), glow)
        base.alpha_composite(sp, xy)
    return view(base.convert("RGB"), *cam).convert("RGBA")


# threads (b_lobl coords): entry 0.5 cm in front of the hairline, on the vertical from the lateral canthus
CANTHUS = (780, 845)
HAIRLINE = (780, 392)
ENTRY = (780, 418)
VECTORS = [
    [ENTRY, (850, 620), (886, 850), (832, 1020), (690, 1172)],
    [ENTRY, (862, 620), (906, 862), (872, 1092), (732, 1322)],
    [ENTRY, (872, 620), (926, 872), (916, 1162), (772, 1462)],
    [ENTRY, (882, 620), (950, 882), (990, 1152), (950, 1424)],
]
PATHS = [catmull(v, n=16) for v in VECTORS]


def path_part(P, frac):
    n = max(2, int(round(len(P) * clamp(frac))))
    return P[:n]


def draw_thread(layer, Pout, width=5, barbs=True, tip=False):
    pts_ = [tuple(p) for p in Pout]
    if len(pts_) < 2:
        return
    glow_line(layer, pts_, width, (238, 232, 255, 245), glow=7, glow_a=170)
    d = ImageDraw.Draw(layer)
    if barbs:
        acc = 0.0
        for i in range(1, len(pts_)):
            (x0, y0), (x1, y1) = pts_[i - 1], pts_[i]
            L = math.hypot(x1 - x0, y1 - y0)
            acc += L
            if acc > 26 and L > 0:
                acc = 0
                ux, uy = (x1 - x0) / L, (y1 - y0) / L
                for sgn in (1, -1):
                    nx, ny = -uy * sgn, ux * sgn
                    d.line([(x1, y1), (x1 - ux * 9 + nx * 8, y1 - uy * 9 + ny * 8)],
                           fill=(255, 255, 255, 235), width=2)
    if tip:
        x, y = pts_[-1]
        g = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((x - 16, y - 16, x + 16, y + 16), fill=(255, 255, 255, 200))
        layer.alpha_composite(g.filter(ImageFilter.GaussianBlur(7)))
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=WHITE)


# ------------------------------------------------------------------ spheres (macro scene)
def sphere_sprite(base, n=256, seed=0, bubble=False):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2
    x, y = (xx - c) / (c * 0.92), (yy - c) / (c * 0.92)
    r2 = x * x + y * y
    z = np.sqrt(np.clip(1 - r2, 0, 1))
    small = rng.normal(0, 1, (12, 12))
    bump = np.asarray(Image.fromarray(((small - small.min()) / np.ptp(small) * 255).astype(np.uint8))
                      .resize((n, n), Image.Resampling.BICUBIC), float) / 255 - 0.5
    bx = np.gradient(bump, axis=1) * 30
    by = np.gradient(bump, axis=0) * 30
    nx, ny, nz = x + bx * 0.25, y + by * 0.25, z
    ln = np.array([-0.45, -0.55, 0.70])
    ln /= np.linalg.norm(ln)
    diff = np.clip(nx * ln[0] + ny * ln[1] + nz * ln[2], 0, 1)
    spec = np.clip(diff, 0, 1) ** 22
    rim = (1 - z) ** 2.2
    base = np.array(base, float)
    if bubble:
        col = base * 0.5 + 255 * 0.5 * rim[..., None] + spec[..., None] * 255
        a = np.clip(0.18 + 0.8 * rim + spec, 0, 1)
    else:
        col = base * (0.32 + 0.78 * diff[..., None]) + rim[..., None] * np.array([120, 90, 150]) * 0.55 \
            + spec[..., None] * 230
        a = np.ones_like(z)
    edge = np.clip((1 - np.sqrt(r2)) * c * 0.92 / 2.0, 0, 1)
    a = a * edge
    col = np.clip(col, 0, 255)
    col[edge <= 0] = base * 0.7
    im = Image.fromarray(np.dstack([col, a * 255]).astype(np.uint8), "RGBA")
    return [im] + [im.filter(ImageFilter.GaussianBlur(b)) for b in (4, 9, 16, 26)]


SPH = [sphere_sprite((122, 82, 206), seed=1), sphere_sprite((150, 112, 226), seed=2),
       sphere_sprite((92, 58, 176), seed=3)]
BUB = sphere_sprite((150, 170, 255), seed=4, bubble=True)
BLUR_LV = (0, 4, 9, 16, 26)


def put_sphere(dst, sprites, x, y, diam, blur_px, a=1.0):
    diam = int(diam)
    if diam < 3 or x + diam < 0 or x - diam > W or y + diam < 0 or y - diam > H:
        return
    need = blur_px * 256 / max(diam, 1)
    lv = min(range(5), key=lambda i: abs(BLUR_LV[i] - need))
    sp = sprites[lv].resize((diam, diam), Image.Resampling.BILINEAR)
    paste(dst, sp, x - diam / 2, y - diam / 2, a)


def bg_lavender():
    yy = np.linspace(0, 1, H)[:, None]
    top, bot = np.array([248, 246, 252]), np.array([214, 202, 240])
    g = top * (1 - yy) + bot * yy
    g = np.repeat(g[:, None, :], W, axis=1).reshape(H, W, 3)
    xx = np.linspace(-1, 1, W)[None, :]
    vign = 1 - 0.10 * (xx ** 2)
    return Image.fromarray(np.clip(g * vign[..., None], 0, 255).astype(np.uint8)).convert("RGBA")


BG_LAV = bg_lavender()
RNG = np.random.default_rng(11)
FIELD = [dict(x=RNG.uniform(-900, 900), y=RNG.uniform(-1500, 1500), z=RNG.uniform(500, 3200),
              r=RNG.uniform(40, 130), k=int(RNG.integers(0, 3)), vy=RNG.uniform(-60, 60),
              vx=RNG.uniform(-30, 30)) for _ in range(46)]


def sphere_field(dst, t, drift=(0, 0), dolly=0.0, focus=1100):
    items = []
    for s in FIELD:
        z = s["z"] - dolly
        if z < 160:
            z += 2800
        x = s["x"] + (s["vx"] + drift[0]) * t
        y = s["y"] + (s["vy"] + drift[1]) * t
        f = 900 / z
        items.append((z, W / 2 + x * f, H / 2 + y * f, 2 * s["r"] * f,
                      abs(1 / z - 1 / focus) * 26000, s["k"]))
    for z, x, y, d, b, k in sorted(items, key=lambda i: -i[0]):
        put_sphere(dst, SPH[k], x, y, d, b)


def thread_macro(layer, P0, P1, width=26, phase=0.0):
    d = ImageDraw.Draw(layer)
    glow_line(layer, [P0, P1], width, (246, 242, 255, 235), glow=16, glow_a=160)
    d.line([P0, P1], fill=(196, 176, 240, 255), width=max(2, width // 5))
    L = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
    ux, uy = (P1[0] - P0[0]) / L, (P1[1] - P0[1]) / L
    nx, ny = -uy, ux
    step = 70
    n = int(L / step)
    for i in range(n):
        s = (i + (phase % 1)) * step
        x, y = P0[0] + ux * s, P0[1] + uy * s
        sg = 1 if i % 2 == 0 else -1
        tipx = x - ux * 34 + nx * sg * (width * 0.5 + 22)
        tipy = y - uy * 34 + ny * sg * (width * 0.5 + 22)
        d.polygon([(x + nx * sg * width * 0.4, y + ny * sg * width * 0.4),
                   (x + ux * 18 + nx * sg * width * 0.4, y + uy * 18 + ny * sg * width * 0.4),
                   (tipx, tipy)], fill=(232, 224, 255, 240), outline=(170, 150, 230, 255))


# ------------------------------------------------------------------ scenes
T_BEFORE = (0.0, 5.6)
T_WIPE = (5.6, 11.6)
T_ANAT = (11.6, 16.6)
T_AGE = (16.6, 21.6)
T_MARK = (21.6, 26.0)
T_THREAD = (26.0, 31.6)
T_MACRO = (31.6, 38.0)
T_FINAL = (38.0, 45.0)


def sc_before(u):
    i = min(3, int(u / 1.4))
    k = ORDER[i]
    lu = u - i * 1.4
    cx, cy, s = photo_cam("b_" + k, zoom=1.0 + 0.05 * lu / 1.4)
    fr = view(IMG["b_" + k], cx, cy, s).convert("RGBA")
    if lu < 0.25 and i > 0:
        pk = ORDER[i - 1]
        pc = photo_cam("b_" + pk, zoom=1.05 + 0.01 * lu)
        prev = view(IMG["b_" + pk], *pc).convert("RGBA")
        fr = Image.blend(prev, fr, ease(lu / 0.25))
    put_center(fr, title("NON-SURGICAL LIFT", "არაქირურგიული ლიფტინგი"), 150, ease_out(u / 0.5), 30)
    put_center(fr, cap("with NAMICA threads", "NAMICA-ს ძაფებით", 38, 30), 420, ease_out((u - 0.3) / 0.5), 20)
    put_center(fr, tag("BEFORE", "მანამდე"), 1500, ease_out((u - 0.2) / 0.4))
    return fr


def sc_wipe(u):
    i = min(3, int(u / 1.5))
    k = ORDER[i]
    lu = u - i * 1.5
    cam = photo_cam("b_" + k, zoom=1.0 + 0.06 * lu / 1.5)
    bf = view(IMG["b_" + k], *cam)
    af = view(IMG["a_" + k], *cam, M=ALIGN[k])
    left = PHOTOS["b_" + k]["left"]
    p = ease_io(seg(lu, 0.2, 1.0))
    X = int(W * p) if left else int(W * (1 - p))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rectangle((0, 0, X, H) if left else (X, 0, W, H), fill=255)
    fr = Image.composite(af, bf, m).convert("RGBA")
    if 0 < p < 1:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_line(lay, [(X, 0), (X, H)], 4, (255, 255, 255, 255), glow=12, glow_a=200)
        fr.alpha_composite(lay)
    put_center(fr, cap("Immediately after the procedure", "უშუალოდ პროცედურის შემდეგ", 40, 31), 150,
               ease_out(u / 0.4), 20)
    after = p > 0.5
    put_center(fr, tag("AFTER", "შემდეგ") if after else tag("BEFORE", "მანამდე", (70, 60, 90)),
               1500)
    return fr


def sc_anat(u):
    cam = cam_lerp((850, 1000, 1.08), ANAT_CAM, ease_io(u / 1.2))
    alphas = [ease_out((u - 0.5 - j * 0.22) / 0.35) for j in range(len(COMPS))]
    fr = anatomy_frame(cam, 0, 0, alphas)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for j, (en, ka, ci, ly) in enumerate(LABELS):
        a = ease_out((u - 1.6 - j * 0.32) / 0.3)
        if a <= 0:
            continue
        im = label_img(en, ka)
        x = 1060 - im.width
        cx_, cy_ = to_out(COMPS[ci]["cen"], cam)
        d.line([(x, ly + im.height / 2), (cx_, cy_)], fill=(255, 255, 255, int(210 * a)), width=2)
        d.ellipse((cx_ - 6, cy_ - 6, cx_ + 6, cy_ + 6), fill=(255, 255, 255, int(255 * a)))
        paste(lay, im, x + (1 - a) * 30, ly, a)
    fr.alpha_composite(lay)
    put_center(fr, cap("Facial fat sits in separate compartments",
                       "სახის ცხიმი ცალკეულ კომპარტმენტებშია განლაგებული"), 130, ease_out(u / 0.4), 20)
    return fr


def labels_fade(fr, cam, a, age=0, lift=0):
    if a <= 0:
        return
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for en, ka, ci, ly in LABELS:
        im = label_img(en, ka)
        x = 1060 - im.width
        off, _ = comp_state(COMPS[ci], age, lift)
        cx_, cy_ = to_out(COMPS[ci]["cen"] + off, cam)
        d.line([(x, ly + im.height / 2), (cx_, cy_)], fill=(255, 255, 255, int(210 * a)), width=2)
        d.ellipse((cx_ - 6, cy_ - 6, cx_ + 6, cy_ + 6), fill=(255, 255, 255, int(255 * a)))
        paste(lay, im, x, ly, a)
    fr.alpha_composite(lay)


def sc_age(u):
    cam = ANAT_CAM
    age = ease_io(seg(u, 0.6, 4.4))
    fr = anatomy_frame(cam, age, 0, [1] * len(COMPS))
    labels_fade(fr, cam, 1 - ease(u / 0.5), age)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if 0.6 < u < 4.6:
        for ci in (6, 7, 8, 10, 11, 4):
            off, _ = comp_state(COMPS[ci], age, 0)
            x, y = to_out(COMPS[ci]["cen"] + off, cam)
            ph = (u * 1.6 + ci * 0.17) % 1
            for kk in range(2):
                chevron(d, x, y - 26 + kk * 22 + ph * 16, 18, False,
                        (255, 255, 255, int(230 * math.sin(math.pi * ph))), 5)
    fr.alpha_composite(lay)
    years = int(round(lerp(35, 65, age)))
    yi = block(((f"{years}", F_BLACK, 110, WHITE, None, 0, 0, 0),
                ("years · წელი", F_KA_B, 30, WHITE, PURPLE + (230,), 14, 6, 0)), 400)
    paste(fr, yi, 1050 - yi.width, 420, ease_out(u / 0.4))
    put_center(fr, cap("With age, compartments lose volume and slide down",
                       "ასაკთან ერთად ისინი მოცულობას კარგავენ და ქვემოთ ინაცვლებენ"), 130,
               ease_out(u / 0.4), 20)
    put_center(fr, cap("Ligaments loosen → jowls & deeper folds",
                       "იოგები სუსტდება → ბრილები და ღრმა ნაოჭები", 36, 29,
                       en_bg=(20, 12, 40, 210)), 1520, ease_out((u - 2.2) / 0.4), 20)
    return fr


MARK_CAM = (880, 640, 0.56)


def sc_mark(u):
    zoom_out = ease_io(seg(u, 2.4, 3.6))
    cam = cam_lerp(cam_lerp(ANAT_CAM, MARK_CAM, ease_io(u / 0.7)), ANAT_CAM, zoom_out)
    fr = anatomy_frame(cam, 1, 0, [0.42] * len(COMPS))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = to_out(CANTHUS, cam)
    hl = to_out(HAIRLINE, cam)
    en = to_out(ENTRY, cam)
    lab_a = 1 - zoom_out
    # canthus dot
    a1 = ease_out((u - 0.5) / 0.3)
    if a1 > 0:
        d.ellipse((c[0] - 9, c[1] - 9, c[0] + 9, c[1] + 9), fill=GOLD + (int(255 * a1),), outline=WHITE, width=2)
    # vertical line up to hairline
    g = ease_io(seg(u, 0.7, 1.4))
    if g > 0:
        dashed(d, [c, (c[0], lerp(c[1], hl[1], g))], GOLD + (240,), 4, 18, 10)
    a2 = ease_out((u - 1.3) / 0.3)
    if a2 > 0:
        d.line([(hl[0] - 70, hl[1]), (hl[0] + 70, hl[1])], fill=(255, 255, 255, int(230 * a2)), width=3)
    a3 = ease_out((u - 1.6) / 0.3)
    if a3 > 0:
        # 0.5 cm bracket
        bx = hl[0] - 34
        d.line([(bx, hl[1]), (bx, en[1])], fill=(255, 255, 255, int(255 * a3)), width=3)
        for yy in (hl[1], en[1]):
            d.line([(bx - 9, yy), (bx + 9, yy)], fill=(255, 255, 255, int(255 * a3)), width=3)
        pr = 1 + 0.25 * math.sin(u * 7)
        g2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g2).ellipse((en[0] - 26 * pr, en[1] - 26 * pr, en[0] + 26 * pr, en[1] + 26 * pr),
                                   fill=PURPLE + (int(200 * a3),))
        lay.alpha_composite(g2.filter(ImageFilter.GaussianBlur(8)))
        d.ellipse((en[0] - 11, en[1] - 11, en[0] + 11, en[1] + 11), fill=WHITE, outline=PURPLE, width=4)
    # vectors (dashed) fan out while zooming out
    vf = ease_io(seg(u, 2.6, 4.0))
    if vf > 0:
        for P in PATHS:
            Pp = [to_out(p, cam) for p in path_part(P, vf)]
            dashed(d, Pp, (255, 255, 255, 220), 3, 12, 9)
            if vf > 0.98:
                x, y = Pp[-1]
                d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=PURPLE + (255,), outline=WHITE, width=2)
    fr.alpha_composite(lay)
    if lab_a > 0:
        if a1 > 0:
            im = block((("Lateral canthus", F_BOLD, 28, WHITE, (20, 12, 40, 210), 12, 6, 0),
                        ("თვალის გარე კუთხე", F_KA, 23, WHITE, (20, 12, 40, 210), 12, 5, 0)), 500, "l")
            paste(fr, im, c[0] + 40, c[1] - 10, a1 * lab_a)
        if a2 > 0:
            im = block((("Hairline", F_BOLD, 28, WHITE, (20, 12, 40, 210), 12, 6, 0),
                        ("თმის ზრდის ხაზი", F_KA, 23, WHITE, (20, 12, 40, 210), 12, 5, 0)), 500, "l")
            paste(fr, im, hl[0] + 90, hl[1] - im.height - 6, a2 * lab_a)
        if a3 > 0:
            im = block((("ENTRY POINT · 0.5 cm", F_BLACK, 30, WHITE, PURPLE + (240,), 12, 6, 0),
                        ("შესვლის წერტილი · 0,5 სმ", F_KA_B, 24, WHITE, PURPLE_D + (230,), 12, 5, 0)), 600, "l")
            paste(fr, im, en[0] + 46, en[1] - 6, a3 * lab_a)
    put_center(fr, cap("Entry point: vertical line from the lateral canthus, 0.5 cm before the hairline",
                       "შესვლის წერტილი: თვალის გარე კუთხიდან ვერტიკალზე, თმის ხაზამდე 0,5 სმ-ით ადრე",
                       38, 29), 130, ease_out(u / 0.4), 20)
    return fr


BASE_ALOBL = None


def sc_thread(u):
    global BASE_ALOBL
    cam = ANAT_CAM
    lift = ease_io(seg(u, 3.0, 4.6))
    xf = ease(seg(u, 4.5, 5.6))
    alphas = [lerp(0.42, 0.9, ease(seg(u, 2.6, 3.2))) * (1 - xf)] * len(COMPS)
    fr = anatomy_frame(cam, 1, lift, alphas, glow=0.25 * math.sin(math.pi * seg(u, 3.0, 4.6)))
    if xf > 0:
        if BASE_ALOBL is None:
            BASE_ALOBL = view(IMG["a_lobl"], *cam, M=ALIGN["lobl"]).convert("RGBA")
        fr = Image.blend(fr, BASE_ALOBL, xf)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ta = 1 - xf
    for j, P in enumerate(PATHS):
        prog = ease_io(seg(u, 0.3 + j * 0.45, 1.5 + j * 0.45))
        if prog <= 0:
            continue
        Pout = [to_out(p, cam) for p in path_part(P, prog)]
        draw_thread(lay, Pout, 5, barbs=True, tip=prog < 1)
    d = ImageDraw.Draw(lay)
    if 3.0 < u < 4.8:
        for P in PATHS:
            for kk in range(3):
                f = 0.85 - ((u * 0.9 + kk / 3) % 1) * 0.6
                i = int(f * (len(P) - 1))
                x, y = to_out(P[i], cam)
                x2, y2 = to_out(P[max(0, i - 3)], cam)
                ang = math.atan2(y2 - y, x2 - x)
                aa = int(255 * math.sin(math.pi * seg(u, 3.0, 4.8)))
                for sgn in (1, -1):
                    d.line([(x + math.cos(ang) * 14, y + math.sin(ang) * 14),
                            (x + math.cos(ang + sgn * 2.5) * 14, y + math.sin(ang + sgn * 2.5) * 14)],
                           fill=GOLD + (aa,), width=5)
    if ta < 1:
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * ta)))
    fr.alpha_composite(lay)
    if u < 4.6:
        put_center(fr, cap("Cogged NAMICA threads lift the compartments back into place",
                           "NAMICA-ს კბილანებიანი ძაფები კომპარტმენტებს ადგილზე აბრუნებს"), 130,
                   ease_out(u / 0.4) * (1 - ease(seg(u, 4.3, 4.6))), 20)
    else:
        put_center(fr, tag("AFTER", "შემდეგ"), 1500, ease_out((u - 4.6) / 0.4))
    return fr


def sc_macro(u):
    fr = BG_LAV.copy()
    sub = min(2, int(u / 2.13))
    lu = u - sub * 2.13
    if sub == 0:      # LIFTING
        sphere_field(fr, u, drift=(0, -40), dolly=u * 120)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        P0, P1 = (-60, 1720), (1140, 260)
        ux, uy = (P1[0] - P0[0]), (P1[1] - P0[1])
        L = math.hypot(ux, uy)
        ux, uy = ux / L, uy / L
        mv = ease_io(seg(lu, 0.3, 1.8)) * 300
        rng = np.random.default_rng(5)
        cl = [(rng.uniform(-160, 160), rng.uniform(-220, 220), rng.uniform(70, 130)) for _ in range(11)]
        thread_macro(lay, P0, P1, 26, phase=-mv / 70)
        for ox, oy, r in sorted(cl, key=lambda c: c[2]):
            cx, cy = 560 + ox + ux * mv, 1150 + oy + uy * mv
            put_sphere(lay, SPH[0], cx, cy, 2 * r, 1)
        thread_macro(lay, (P0[0] + ux * 540, P0[1] + uy * 540), (P0[0] + ux * 900, P0[1] + uy * 900), 26, -mv / 70)
        fr.alpha_composite(lay)
        t_en, t_ka = "LIFTING", "ლიფტინგი"
        s_en, s_ka = "Cogs grip and lift the tissue instantly", "კბილანები ქსოვილს მყისიერად ზემოთ სწევს"
    elif sub == 1:    # BIOSTIMULATION
        sphere_field(fr, u, drift=(30, 0), dolly=u * 80)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        P0, P1 = (-80, 1280), (1160, 1060)
        L = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
        ux, uy = (P1[0] - P0[0]) / L, (P1[1] - P0[1]) / L
        nx, ny = -uy, ux
        grow = ease_out(seg(lu, 0.2, 1.9))
        rng = np.random.default_rng(9)
        for _ in range(70):
            s0 = rng.uniform(0, L)
            sg = rng.choice([-1, 1])
            ln = rng.uniform(120, 420) * grow
            amp, fq, ph = rng.uniform(6, 18), rng.uniform(0.015, 0.03), rng.uniform(0, 6)
            ang = rng.uniform(-0.6, 0.6)
            dx = nx * sg * math.cos(ang) + ux * math.sin(ang)
            dy = ny * sg * math.cos(ang) + uy * math.sin(ang)
            bx, by = P0[0] + ux * s0, P0[1] + uy * s0
            P = []
            for k in range(0, int(ln) + 1, 8):
                w = amp * math.sin(k * fq * 6.28 + ph + u * 2)
                P.append((bx + dx * k - dy * w, by + dy * k + dx * w))
            if len(P) > 1:
                d.line(P, fill=(255, 250, 255, 190), width=4, joint="curve")
                d.line(P, fill=(190, 160, 240, 200), width=1)
        # particle stream along the thread
        for k in range(60):
            f = ((k / 60) + u * 0.25) % 1
            x = P0[0] + ux * L * f + nx * math.sin(k * 1.7 + u * 3) * 40
            y = P0[1] + uy * L * f + ny * math.sin(k * 1.7 + u * 3) * 40
            put_sphere(lay, SPH[1], x, y, 14 + (k % 5) * 6, 0)
        thread_macro(lay, P0, P1, 24, phase=u * 0.4)
        fr.alpha_composite(lay)
        t_en, t_ka = "BIOSTIMULATION", "ბიოსტიმულაცია"
        s_en, s_ka = "New collagen forms around the thread", "ძაფის გარშემო ახალი კოლაგენი წარმოიქმნება"
    else:             # HYDRATION
        sphere_field(fr, u, drift=(0, 30), dolly=u * 60)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        P0, P1 = (300, -60), (780, 1980)
        L = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
        ux, uy = (P1[0] - P0[0]) / L, (P1[1] - P0[1]) / L
        nx, ny = -uy, ux
        rng = np.random.default_rng(13)
        for k in range(90):
            s0 = rng.uniform(0.05, 0.95) * L
            t0 = rng.uniform(0, 1.2)
            sg = rng.choice([-1, 1])
            ang = rng.uniform(-0.9, 0.9)
            age = lu - t0
            if age <= 0:
                continue
            dist = 30 + age * rng.uniform(140, 320)
            dx = nx * sg * math.cos(ang) + ux * math.sin(ang)
            dy = ny * sg * math.cos(ang) + uy * math.sin(ang)
            x = P0[0] + ux * s0 + dx * dist
            y = P0[1] + uy * s0 + dy * dist
            put_sphere(lay, BUB, x, y, 16 + age * rng.uniform(30, 70), 0, clamp(1.4 - age * 0.5))
        thread_macro(lay, P0, P1, 26, phase=u * 0.3)
        fr.alpha_composite(lay)
        for k in range(6):
            put_sphere(fr, BUB, 120 + k * 190, 1500 - (lu * 120 + k * 230) % 1300, 180 + k * 25, 14, 0.7)
        t_en, t_ka = "HYDRATION", "დატენიანება"
        s_en, s_ka = "Hyaluronic acid inside the thread hydrates the skin", "ძაფში არსებული ჰიალურონის მჟავა კანს ატენიანებს"
    a = ease_out(lu / 0.35) * (1 - ease(seg(lu, 1.95, 2.13)) if sub < 2 else ease_out(lu / 0.35))
    put_center(fr, title(t_en, t_ka, 88, 44), 300, a, 30)
    put_center(fr, cap(s_en, s_ka, 36, 29, en_bg=PURPLE_D + (225,), ka_bg=PURPLE_D + (200,)), 540,
               ease_out((lu - 0.2) / 0.35), 20)
    return fr


@lru_cache(None)
def final_panels():
    cw, ch = 516, 1000
    cam = ANAT_CAM
    cx, cy, s = 760, 1000, 1.55
    b = view(IMG["b_lobl"], cx, cy, s, (cw, ch)).convert("RGBA")
    a = view(IMG["a_lobl"], cx, cy, s, (cw, ch), M=ALIGN["lobl"]).convert("RGBA")
    m = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=28, fill=255)
    out = []
    for im in (b, a):
        o = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        o.paste(im, (0, 0), m)
        out.append(o)
    return out


def sc_final(u):
    fr = Image.new("RGBA", (W, H), (14, 10, 24, 255))
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse((-200, 300, 1280, 1700), fill=PURPLE + (70,))
    fr.alpha_composite(g.filter(ImageFilter.GaussianBlur(120)))
    b, a = final_panels()
    k1, k2 = ease_out(u / 0.6), ease_out((u - 0.25) / 0.6)
    paste(fr, b, 16, 330 + (1 - k1) * 60, k1)
    paste(fr, a, 548, 330 + (1 - k2) * 60, k2)
    put_center(fr, title("THE RESULT", "შედეგი"), 130, ease_out(u / 0.5), 30)
    tb, ta = tag("BEFORE", "მანამდე", (70, 60, 90)), tag("AFTER", "შემდეგ")
    paste(fr, tb, 16 + (516 - tb.width) / 2, 1250, k1)
    paste(fr, ta, 548 + (516 - ta.width) / 2, 1250, k2)
    bd = badge(190, 42, 34)
    paste(fr, bd, (W - bd.width) / 2, 1380, ease_out((u - 0.8) / 0.5))
    put_center(fr, cap("Book your consultation", "დაჯავშნე კონსულტაცია", 44, 34), 1620,
               ease_out((u - 1.2) / 0.5), 20)
    return fr


SCENES = [(T_BEFORE, sc_before), (T_WIPE, sc_wipe), (T_ANAT, sc_anat), (T_AGE, sc_age),
          (T_MARK, sc_mark), (T_THREAD, sc_thread), (T_MACRO, sc_macro), (T_FINAL, sc_final)]
XF = 0.3


def frame(t):
    for i, ((a, b), fn) in enumerate(SCENES):
        if a <= t < b or i == len(SCENES) - 1:
            fr = fn(t - a)
            if i > 0 and t - a < XF:
                (pa, _), pfn = SCENES[i - 1]
                prev = pfn(t - pa)
                fr = Image.blend(prev, fr, ease((t - a) / XF))
            break
    if t < T_FINAL[0]:
        bd = badge()
        paste(fr, bd, 20, 1610, ease_out((t - 0.6) / 0.5) * (1 - ease(seg(t, T_FINAL[0] - 0.3, T_FINAL[0]))))
    if t > DUR - 0.4:
        fr = Image.blend(fr, Image.new("RGBA", (W, H), (0, 0, 0, 255)), ease((t - (DUR - 0.4)) / 0.4))
    return fr.convert("RGB")


def main():
    if sys.argv[1] == "--stills":
        out = sys.argv[2]
        os.makedirs(out, exist_ok=True)
        for s in sys.argv[3:]:
            frame(float(s)).save(os.path.join(out, f"t{float(s):05.2f}.png"))
            print("still", s, flush=True)
        return
    outp = sys.argv[1]
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", outp], stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    for i in range(n):
        p.stdin.write(frame(i / FPS).tobytes())
        if i % 90 == 0:
            print(f"frame {i}/{n}", flush=True)
    p.stdin.close()
    p.wait()


if __name__ == "__main__":
    main()
