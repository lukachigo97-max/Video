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


def view_after(k, cam, size=(W, H), under=None):
    """After photo aligned onto the before framing; edges the rotation leaves empty come from `under`."""
    af = view(IMG["a_" + k], *cam, size=size, M=ALIGN[k])
    if under is None:
        return af
    m = Image.new("L", IMG["a_" + k].size, 255).transform(
        size, Image.Transform.AFFINE, _coeffs(cam, size, ALIGN[k]), fillcolor=0)
    m = m.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(6))
    return Image.composite(af, under, m)


def _coeffs(cam, size, M):
    cx, cy, s = cam
    ox, oy = cx - s * size[0] / 2, cy - s * size[1] / 2
    a, b, tx, ty = M
    return (a * s, -b * s, a * ox - b * oy + tx, b * s, a * s, b * ox + a * oy + ty)


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


# ------------------------------------------------------------------ fat compartments
TEX_O = (120, 280)


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

# Compartments drawn on b_robl (right oblique), after the superficial fat pad anatomy.
# name, outline points, aging shift (dx, dy), aging scale (sx, sy)
COMPS = [
    ("central forehead", [(782, 400), (852, 392), (892, 450), (898, 580), (866, 640), (800, 642), (770, 560), (765, 460)], (0, 10), (1, .98)),
    ("middle forehead", [(560, 425), (690, 395), (752, 420), (760, 560), (742, 630), (620, 642), (520, 622), (508, 520)], (0, 14), (1, .97)),
    ("lateral temporal-cheek", [(420, 470), (470, 520), (446, 640), (414, 800), (404, 980), (412, 1150), (424, 1300), (384, 1392), (322, 1352), (292, 1200), (272, 1000), (282, 800), (322, 620), (362, 500)], (0, 24), (.97, 1.03)),
    ("superior orbital", [(522, 706), (622, 696), (742, 702), (770, 730), (740, 768), (640, 778), (542, 768), (507, 740)], (0, 16), (1, .9)),
    ("inferior orbital", [(642, 882), (732, 876), (792, 886), (782, 922), (702, 932), (642, 917)], (0, 22), (.95, .85)),
    ("lateral orbital", [(482, 782), (582, 777), (620, 832), (602, 912), (532, 932), (472, 882)], (2, 22), (.94, .92)),
    ("medial cheek", [(702, 952), (802, 942), (862, 992), (852, 1082), (782, 1122), (702, 1102), (672, 1022)], (6, 58), (.9, .92)),
    ("middle cheek", [(522, 962), (642, 952), (690, 1012), (700, 1150), (652, 1232), (572, 1212), (512, 1102), (502, 1012)], (6, 46), (.94, .97)),
    ("nasolabial", [(842, 1110), (874, 1122), (836, 1192), (774, 1262), (738, 1252), (762, 1182), (802, 1132)], (8, 40), (1.12, 1.03)),
    ("superior jowl", [(622, 1282), (702, 1292), (722, 1342), (702, 1402), (632, 1402), (592, 1352)], (0, 50), (1.06, 1.05)),
    ("inferior jowl", [(602, 1422), (722, 1422), (782, 1462), (762, 1532), (662, 1552), (592, 1512), (572, 1462)], (0, 52), (1.1, 1.06)),
    ("submandibular", [(402, 1422), (522, 1442), (566, 1482), (550, 1540), (462, 1522), (372, 1482)], (0, 44), (1.06, 1.05)),
]
for i, c in enumerate(COMPS):
    sm = catmull(c[1], closed=True, n=8)
    COMPS[i] = dict(name=c[0], smooth=sm, cen=sm.mean(0), d=np.array(c[2], float), s=np.array(c[3], float))

# label groups: EN, KA, anchor compartment, label y (output px, anatomy camera); column on the left
LABELS = [
    ("Forehead fat", "შუბლის ცხიმი", 1, 560),
    ("Lateral temporal-cheek fat", "საფეთქელ-ლოყის ლატ. ცხიმი", 2, 715),
    ("Orbital fat", "ორბიტული ცხიმი", 5, 865),
    ("Middle cheek fat", "ლოყის შუა ცხიმი", 7, 1015),
    ("Medial cheek fat", "ლოყის მედიალური ცხიმი", 6, 1165),
    ("Nasolabial fat", "ნაზოლაბიური ცხიმი", 8, 1315),
    ("Jowl fat", "ბრილების ცხიმი", 10, 1465),
]
LABEL_X = 20

# Marking from the reference sketch (5 lifting vectors fanning forward from one point in front
# of the ear), traced in the sketch and mapped onto b_robl with an affine fit on eye, nose tip,
# mouth corner and ear landmarks.
_REF = np.array([(185, 18), (248, 65), (195, 100), (88, 45)], float)
_DST = np.array([(712, 830), (1034, 1034), (718, 1271), (200, 1000)], float)
_AFF = np.linalg.lstsq(np.hstack([_REF, np.ones((4, 1))]), _DST, rcond=None)[0]
_ARROWS = [
    [(115, 20), (120, 35), (140, 52), (160, 60), (185, 65)],
    [(115, 20), (117, 42), (140, 65), (160, 73), (182, 78)],
    [(115, 20), (116, 55), (135, 80), (155, 89), (180, 93)],
    [(115, 20), (120, 75), (140, 100), (155, 110), (175, 116)],
    [(115, 20), (111, 62), (122, 100), (145, 120), (172, 130)],
]
PATHS = [catmull([tuple(np.array([x, y, 1.0]) @ _AFF) for x, y in a], n=16) for a in _ARROWS]
ORIGIN = PATHS[0][0]


@lru_cache(None)
def label_img(en, ka):
    return block(((en, F_BOLD, 25, (30, 20, 50), (255, 255, 255, 236), 14, 6, 0),
                  (ka, F_KA, 20, (60, 40, 100), (255, 255, 255, 236), 14, 5, 0)), 400, align="l")


def comp_state(c, age, lift):
    """age 0..1 descends; lift 0..1 brings it back (slightly above youthful position)."""
    k = age * (1 - lift)
    off = c["d"] * k
    if lift > 0:   # repositioned up and back, toward the vectors' origin (superolateral)
        v = ORIGIN - c["cen"]
        off = off + v / np.linalg.norm(v) * 16 * lift * age
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


ANAT_CAM = (480, 885, 1.1)
BASE_PHOTO = IMG["b_robl"].convert("RGBA")


def anatomy_frame(cam, age, lift, alphas, glow=0.0, photo=None):
    base = (photo or BASE_PHOTO).copy()
    for c, a in zip(COMPS, alphas):
        if a <= 0.01:
            continue
        off, sc = comp_state(c, age, lift)
        pop = 0.9 + 0.1 * ease_out(a) if a < 1 else 1.0
        sp, xy = comp_sprite(c, off, sc * pop, min(a, 1), glow)
        base.alpha_composite(sp, xy)
    return view(base.convert("RGB"), *cam).convert("RGBA")


def path_part(P, frac):
    n = max(2, int(round(len(P) * clamp(frac))))
    return P[:n]


def draw_thread(layer, Pout, width=5, barbs=True, tip=False):
    pts_ = [tuple(p) for p in Pout]
    if len(pts_) < 2:
        return
    glow_line(layer, pts_, width, (238, 232, 255, 245), glow=7, glow_a=170)
    d = ImageDraw.Draw(layer)
    if barbs:   # fine barbs, flared slightly off the thread and pointing back toward its origin
        acc, side = 0.0, 1
        for i in range(1, len(pts_)):
            (x0, y0), (x1, y1) = pts_[i - 1], pts_[i]
            L = math.hypot(x1 - x0, y1 - y0)
            acc += L
            if acc > 16 and L > 0:
                acc = 0
                side = -side
                ux, uy = (x1 - x0) / L, (y1 - y0) / L
                nx, ny = -uy * side, ux * side
                d.line([(x1 + nx * 1.5, y1 + ny * 1.5), (x1 - ux * 11 + nx * 5, y1 - uy * 11 + ny * 5)],
                       fill=(255, 255, 255, 230), width=2)
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
    step = 46       # barbs: thin slivers cut into the thread, flared at a shallow angle
    n = int(L / step) + 2
    for i in range(-1, n):
        s_ = (i + (phase % 1)) * step
        x, y = P0[0] + ux * s_, P0[1] + uy * s_
        sg = 1 if i % 2 == 0 else -1
        r = width * 0.5
        base1 = (x + nx * sg * r * 0.55, y + ny * sg * r * 0.55)
        base2 = (x - ux * 30 + nx * sg * r * 0.75, y - uy * 30 + ny * sg * r * 0.75)
        tip = (x - ux * 44 + nx * sg * (r + 13), y - uy * 44 + ny * sg * (r + 13))
        d.polygon([base1, tip, base2], fill=(236, 230, 255, 245), outline=(160, 138, 226, 255))
        d.line([base1, base2], fill=(150, 126, 220, 255), width=2)


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


WIPE_ORDER = ["robl", "rprof"]   # right side compares best


def sc_wipe(u):
    i = min(1, int(u / 3.0))
    k = WIPE_ORDER[i]
    lu = u - i * 3.0
    cam = photo_cam("b_" + k, zoom=1.0 + 0.07 * lu / 3.0)
    bf = view(IMG["b_" + k], *cam)
    af = view_after(k, cam, under=bf)
    left = PHOTOS["b_" + k]["left"]
    p = ease_io(seg(lu, 0.4, 2.0))
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
    cam = cam_lerp((500, 900, 1.2), ANAT_CAM, ease_io(u / 1.2))
    alphas = [ease_out((u - 0.5 - j * 0.22) / 0.35) for j in range(len(COMPS))]
    fr = anatomy_frame(cam, 0, 0, alphas)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for j, (en, ka, ci, ly) in enumerate(LABELS):
        a = ease_out((u - 1.6 - j * 0.32) / 0.3)
        if a <= 0:
            continue
        im = label_img(en, ka)
        x = LABEL_X
        cx_, cy_ = to_out(COMPS[ci]["cen"], cam)
        d.line([(x + im.width, ly + im.height / 2), (cx_, cy_)], fill=(255, 255, 255, int(210 * a)), width=2)
        d.ellipse((cx_ - 6, cy_ - 6, cx_ + 6, cy_ + 6), fill=(255, 255, 255, int(255 * a)))
        paste(lay, im, x - (1 - a) * 30, ly, a)
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
        x = LABEL_X
        off, _ = comp_state(COMPS[ci], age, lift)
        cx_, cy_ = to_out(COMPS[ci]["cen"] + off, cam)
        d.line([(x + im.width, ly + im.height / 2), (cx_, cy_)], fill=(255, 255, 255, int(210 * a)), width=2)
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


def arrow_head(d, P, size, color):
    (x0, y0), (x1, y1) = P[-4], P[-1]
    ang = math.atan2(y1 - y0, x1 - x0)
    tip = (x1 + math.cos(ang) * size * 0.6, y1 + math.sin(ang) * size * 0.6)
    d.polygon([tip, (x1 + math.cos(ang + 2.5) * size, y1 + math.sin(ang + 2.5) * size),
               (x1 + math.cos(ang - 2.5) * size, y1 + math.sin(ang - 2.5) * size)], fill=color)


def sc_mark(u):
    cam = ANAT_CAM
    fr = anatomy_frame(cam, 1, 0, [0.42] * len(COMPS))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for j, P in enumerate(PATHS):
        prog = ease_io(seg(u, 0.4 + j * 0.42, 1.3 + j * 0.42))
        if prog <= 0:
            continue
        Pp = [to_out(p, cam) for p in path_part(P, prog)]
        glow_line(lay, Pp, 6, (255, 255, 255, 250), glow=6, glow_a=140)
        if len(Pp) >= 4:
            arrow_head(ImageDraw.Draw(lay), Pp, 22, (255, 255, 255, 250))
    fr.alpha_composite(lay)
    put_center(fr, cap("Marking the lifting vectors", "ლიფტინგის ვექტორების მარკირება"), 130,
               ease_out(u / 0.4), 20)
    return fr


BASE_AFTER = None


def sc_thread(u):
    global BASE_AFTER
    cam = ANAT_CAM
    lift = ease_io(seg(u, 3.0, 4.6))
    xf = ease(seg(u, 4.5, 5.6))
    alphas = [lerp(0.42, 0.9, ease(seg(u, 2.6, 3.2))) * (1 - xf)] * len(COMPS)
    fr = anatomy_frame(cam, 1, lift, alphas, glow=0.25 * math.sin(math.pi * seg(u, 3.0, 4.6)))
    if xf > 0:
        if BASE_AFTER is None:
            BASE_AFTER = view_after("robl", cam, under=view(IMG["b_robl"], *cam)).convert("RGBA")
        fr = Image.blend(fr, BASE_AFTER, xf)
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
        put_center(fr, cap("Barbed NAMICA threads lift the compartments back into place",
                           "NAMICA-ს ბარბებიანი ძაფები კომპარტმენტებს ადგილზე აბრუნებს"), 130,
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
        s_en, s_ka = "Barbs grip and lift the tissue instantly", "ბარბები ქსოვილს ეჭიდება და მყისიერად სწევს ზემოთ"
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
    cx, cy, s = 660, 1000, 1.6
    bv = view(IMG["b_robl"], cx, cy, s, (cw, ch))
    b = bv.convert("RGBA")
    a = view_after("robl", (cx, cy, s), (cw, ch), under=bv).convert("RGBA")
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
