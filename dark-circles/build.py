#!/usr/bin/env python3
"""Re-edit of the "dark circles under the eyes" talking-head reel.

Stage A (ffmpeg): paint the clean wall back over the old burned-in overlays and grade.
Stage B (python): punch-in framing, new photo cards, titles, progress bar and
                  bilingual (Georgian + English) karaoke captions, piped to ffmpeg.

Usage: python3 build.py <original.mov> <work_dir> <output.mp4> [--rebase]
Needs:  fonts/ next to this script (Noto Sans Georgian, Manrope) and
        captions.json (timed Georgian words + English lines).
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, WORK, OUT = sys.argv[1:4]
os.makedirs(WORK, exist_ok=True)
W, H, FPS = 1080, 1920, 30
DUR = 66.5
NF = int(DUR * FPS)

# ------------------------------------------------------------------ palette
INK = (24, 20, 22)
CREAM = (255, 248, 240)
ROSE = (232, 93, 117)       # accent: highlighted word, progress bar, chips
ROSE_DK = (178, 52, 80)
BLUSH = (255, 225, 228)
WHITE = (255, 255, 255)

FD = os.path.join(HERE, "fonts")
KA_900 = os.path.join(FD, "NotoSansGeorgian-900.ttf")
KA_700 = os.path.join(FD, "NotoSansGeorgian-700.ttf")
KA_500 = os.path.join(FD, "NotoSansGeorgian-500.ttf")
EN_800 = os.path.join(FD, "Manrope-800.ttf")
EN_700 = os.path.join(FD, "Manrope-700.ttf")
EN_500 = os.path.join(FD, "Manrope-500.ttf")
_fc = {}


def font(p, s):
    k = (p, s)
    if k not in _fc:
        f = ImageFont.truetype(p, s)
        try:
            f.set_variation_by_axes([int(os.path.basename(p).split("-")[1][:3])])
        except Exception:
            pass
        _fc[k] = f
    return _fc[k]


# ------------------------------------------------------------------ stage A
# old overlays (seconds) -> clean plate time to borrow the wall from
PATCHES = [(0.0, 4.8, 6.5), (18.9, 22.1, 17.0), (28.6, 30.9, 27.5), (49.1, 57.2, 47.5)]
GRADE = ("hqdn3d=2:1.5:3:3,colorchannelmixer=rr=1.045:gg=0.99:bb=0.97,"
         "eq=contrast=1.08:saturation=1.08:gamma=1.03,unsharp=5:5:0.5,vignette=angle=0.3")


def stage_a():
    plates = []
    for i, (_, _, pt) in enumerate(PATCHES):
        p = os.path.join(WORK, f"plate{i}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(pt), "-i", SRC,
                        "-frames:v", "1", p], check=True)
        im = Image.open(p).convert("RGBA")
        a = np.zeros((H, W), np.uint8)
        a[:640] = 255
        for y in range(640, 700):          # feather well above the head (~y 770)
            a[y] = int(255 * (700 - y) / 60)
        im.putalpha(Image.fromarray(a))
        im.save(p)
        plates.append(p)
    args = ["ffmpeg", "-v", "error", "-y", "-i", SRC]
    for p in plates:
        args += ["-i", p]
    fc, last = [], "0:v"
    for i, (a, b, _) in enumerate(PATCHES):
        fc.append(f"[{last}][{i + 1}:v]overlay=0:0:enable='between(t,{a},{b})'[p{i}]")
        last = f"p{i}"
    fc.append(f"[{last}]{GRADE},format=yuv420p[v]")
    base = os.path.join(WORK, "base.mp4")
    args += ["-filter_complex", ";".join(fc), "-map", "[v]", "-an", "-r", str(FPS),
             "-c:v", "libx264", "-crf", "14", "-preset", "fast", base]
    subprocess.run(args, check=True)
    return base


# ------------------------------------------------------------------ helpers
def ease_out_back(x, k=1.70158):
    x = min(max(x, 0.0), 1.0) - 1
    return 1 + (k + 1) * x ** 3 + k * x ** 2


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def shadowed(layer, blur=24, off=14, alpha=110, pad=60):
    """Return layer with a soft drop shadow, padded by `pad` on every side."""
    w, h = layer.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    a = layer.getchannel("A").point(lambda v: v * alpha // 255)
    sh.paste((20, 10, 15, 255), (pad, pad + off), a)
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(layer, (pad, pad))
    return out


def text_w(d, t, f):
    return d.textlength(t, font=f)


# ------------------------------------------------------------------ graphics
def photo_card(path, size, border=12, radius=38):
    """Rounded white-framed photo. Returns (base_photo, frame_fn(kb)) for Ken Burns."""
    src = Image.open(path).convert("RGB")
    w, h = size
    def render(kb):
        # kb in [0,1]: slow push-in inside the frame
        z = 1.0 + 0.07 * kb
        sw, sh = src.size
        scale = max(w / sw, h / sh) * z
        im = src.resize((math.ceil(sw * scale), math.ceil(sh * scale)), Image.LANCZOS)
        x0 = (im.width - w) // 2
        y0 = (im.height - h) // 2
        im = im.crop((x0, y0, x0 + w, y0 + h))
        card = Image.new("RGBA", (w + 2 * border, h + 2 * border), (0, 0, 0, 0))
        m = Image.new("L", card.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius, fill=255)
        card.paste(WHITE + (255,), (0, 0), m)
        m2 = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m2).rounded_rectangle((0, 0, w - 1, h - 1), radius - border, fill=255)
        card.paste(im, (border, border), m2)
        return shadowed(card)
    return render


def chip(ka, en, accent=ROSE):
    """Two-line label: Georgian (bold) over English (small caps-ish)."""
    d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    fk, fe = font(KA_900, 46), font(EN_800, 28)
    en = en.upper()
    tw = max(text_w(d, ka, fk), text_w(d, en, fe) + len(en) * 2.5)
    pw, ph = int(tw + 64), 128
    im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), 30, fill=accent + (255,))
    d.text((32, 40), ka, font=fk, fill=WHITE, anchor="lm")
    x = 32
    for ch in en:                      # letter-spaced English
        d.text((x, 92), ch, font=fe, fill=BLUSH, anchor="lm")
        x += text_w(d, ch, fe) + 2.5
    return shadowed(im, blur=16, off=8, alpha=90, pad=40)


def title_block(ka_lines, en, kicker=None):
    """Big hook title: kicker pill, heavy Georgian lines, English sub."""
    d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    fk, fe, fkk = font(KA_900, 84), font(EN_800, 36), font(EN_800, 26)
    widths = [text_w(d, l, fk) for l in ka_lines]
    tw = max(widths + [text_w(d, en.upper(), fe) + len(en) * 3])
    pw = int(tw + 100)
    ph = 70 + 104 * len(ka_lines) + 70 + (70 if kicker else 0)
    im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), 44, fill=CREAM + (246,))
    y = 52
    if kicker:
        kw = text_w(d, kicker, fkk) + len(kicker) * 3 + 44
        d.rounded_rectangle((50, y - 22, 50 + kw, y + 24), 23, fill=ROSE)
        x = 72
        for ch in kicker:
            d.text((x, y + 1), ch, font=fkk, fill=WHITE, anchor="lm")
            x += text_w(d, ch, fkk) + 3
        y += 70
    for l in ka_lines:
        d.text((50, y + 40), l, font=fk, fill=INK, anchor="lm")
        y += 104
    x = 52
    for ch in en.upper():
        d.text((x, y + 26), ch, font=fe, fill=ROSE_DK, anchor="lm")
        x += text_w(d, ch, fe) + 3
    # accent underline
    d.rounded_rectangle((50, ph - 22, 170, ph - 14), 4, fill=ROSE)
    return shadowed(im, blur=26, off=14, alpha=80)


EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


def emoji_img(ch, size):
    f = ImageFont.truetype(EMOJI, 109)
    im = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((70, 70), ch, font=f, embedded_color=True, anchor="mm")
    im = im.crop(im.getbbox())
    r = size / max(im.size)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


def list_item(icon, ka, en, width=860):
    """Cream pill: rose icon disc, Georgian (bold) + English (small)."""
    h = 112
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, width - 1, h - 1), 56, fill=CREAM + (248,))
    d.ellipse((14, 14, 98, 98), fill=BLUSH)
    e = emoji_img(icon, 50)
    im.alpha_composite(e, (56 - e.width // 2, 56 - e.height // 2))
    d.text((122, 44), ka, font=font(KA_900, 40), fill=INK, anchor="lm")
    d.text((123, 84), en, font=font(EN_700, 27), fill=ROSE_DK, anchor="lm")
    return shadowed(im, blur=18, off=8, alpha=70, pad=40)


# ------------------------------------------------------------------ captions
CAP_Y = 1390           # top of caption block
KA_SIZE, EN_SIZE = 62, 38


def wrap_words(words, f, maxw, d):
    """Greedy wrap, then shrink the width while the line count holds (balanced lines)."""
    n = len(_wrap(words, f, maxw, d))
    lo = maxw
    while lo > 200 and len(_wrap(words, f, lo - 20, d)) == n:
        lo -= 20
    return _wrap(words, f, lo, d)


def _wrap(words, f, maxw, d):
    lines, cur, cw = [], [], 0
    sp = text_w(d, " ", f)
    for i, w in enumerate(words):
        ww = text_w(d, w, f)
        if cur and cw + sp + ww > maxw:
            lines.append(cur)
            cur, cw = [], 0
        cw += (sp if cur else 0) + ww
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def caption_image(group, active):
    """Georgian words (active one on a rose pill) + English line below."""
    d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    fk = font(KA_900, KA_SIZE)
    fe = font(EN_700, EN_SIZE)
    words = [w["w"] for w in group["words"]]
    lines = wrap_words(words, fk, 960, d)
    lh = int(KA_SIZE * 1.42)
    en_lines = []
    for ln in wrap_words(group["en"].split(" "), fe, 900, d):
        en_lines.append(" ".join(group["en"].split(" ")[i] for i in ln))
    eh = int(EN_SIZE * 1.4)
    total_h = lh * len(lines) + 22 + eh * len(en_lines) + 30
    im = Image.new("RGBA", (W, total_h + 40), (0, 0, 0, 0))
    txt = Image.new("RGBA", im.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    pill = Image.new("RGBA", im.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    sp = text_w(d, " ", fk)
    y = 20
    for ln in lines:
        lw = sum(text_w(d, words[i], fk) for i in ln) + sp * (len(ln) - 1)
        x = (W - lw) / 2
        for i in ln:
            ww = text_w(d, words[i], fk)
            if i == active:
                pd.rounded_rectangle((x - 14, y + 4, x + ww + 14, y + lh - 2), 20, fill=ROSE + (255,))
            td.text((x, y + lh / 2 + 2), words[i], font=fk, fill=WHITE, anchor="lm",
                    stroke_width=0 if i == active else 5, stroke_fill=INK + (235,))
            x += ww + sp
        y += lh
    y += 22
    for el in en_lines:
        ew = text_w(d, el, fe)
        pd.rounded_rectangle(((W - ew) / 2 - 22, y - 4, (W + ew) / 2 + 22, y + eh), 16,
                             fill=INK + (190,))
        td.text((W / 2, y + eh / 2 - 1), el, font=fe, fill=CREAM, anchor="mm")
        y += eh + 6
    # soft shadow under everything
    base = Image.alpha_composite(pill, txt)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 255), (0, 6), base.getchannel("A").point(lambda v: v * 90 // 255))
    im = Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), base)
    return im


_capcache = {}


def caption_at(groups, t):
    for gi, g in enumerate(groups):
        if g["start"] <= t < g["end"]:
            act = -1
            for i, w in enumerate(g["words"]):
                if w["s"] <= t + 0.04:
                    act = i
            k = (gi, act)
            if k not in _capcache:
                _capcache[k] = caption_image(g, act)
            age = t - g["start"]
            return _capcache[k], age
    return None, 0


# ------------------------------------------------------------------ timeline
def load_captions():
    with open(os.path.join(HERE, "captions.json"), encoding="utf-8") as f:
        groups = json.load(f)
    for i, g in enumerate(groups):            # hold each group until the next starts
        nxt = groups[i + 1]["start"] if i + 1 < len(groups) else g["end"] + 0.6
        g["end"] = min(max(g["end"] + 0.35, g["end"]), nxt)
    return groups


def build_elements():
    """Each element: dict(kind, start, end, render(t_local)->(img, cx, cy, scale, rot, alpha))."""
    E = []
    P = os.path.join(HERE, "photos")

    def add(start, end, img_fn, cx, cy, rot=0.0, pop=0.45, out=0.3, delay=0.0):
        E.append(dict(start=start + delay, end=end, fn=img_fn, cx=cx, cy=cy, rot=rot,
                      pop=pop, out=out))

    for spec in TIMELINE:
        kind = spec["kind"]
        if kind == "title":
            img = title_block(spec["ka"], spec["en"], spec.get("kicker"))
            add(spec["start"], spec["end"], lambda kb, im=img: im, W / 2, spec.get("cy", 380))
        elif kind == "photo":
            fn = photo_card(os.path.join(P, spec["file"]), spec["size"])
            add(spec["start"], spec["end"], fn, spec["cx"], spec["cy"], spec.get("rot", 0),
                delay=spec.get("delay", 0))
        elif kind == "item":
            img = list_item(spec["icon"], spec["ka"], spec["en"], spec.get("width", 860))
            add(spec["start"], spec["end"], lambda kb, im=img: im, spec.get("cx", W / 2), spec["cy"])
        elif kind == "chip":
            img = chip(spec["ka"], spec["en"])
            add(spec["start"], spec["end"], lambda kb, im=img: im, spec["cx"], spec["cy"],
                spec.get("rot", 0), delay=spec.get("delay", 0))
    return E


def element_frame(e, t):
    if not (e["start"] <= t < e["end"]):
        return None
    lt = t - e["start"]
    dur = e["end"] - e["start"]
    s = 0.6 + 0.4 * ease_out_back(lt / e["pop"])
    a = ease_out(lt / (e["pop"] * 0.6))
    rem = e["end"] - t
    if rem < e["out"]:
        k = rem / e["out"]
        s *= 0.9 + 0.1 * k
        a *= k
    img = e["fn"](min(lt / max(dur, 0.01), 1.0))
    return img, s, a


def place(frame, img, cx, cy, s, rot, a):
    if s != 1.0 or rot:
        w, h = img.size
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BICUBIC)
        if rot:
            img = img.rotate(rot, Image.BICUBIC, expand=True)
    if a < 1.0:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    frame.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


# zoom: (start, end, zoom) segments; anything not listed is 1.0
FACE = (540, 960)


def zoom_at(t):
    for a, b, z in ZOOMS:
        if a <= t < b:
            return z
    return 1.0


def render(base):
    groups = load_captions()
    E = build_elements()
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", base, "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", SRC,
                            "-map", "0:v", "-map", "1:a", "-t", str(DUR),
                            "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                            "-pix_fmt", "yuv420p", "-profile:v", "high",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT],
                           stdin=subprocess.PIPE)
    fsz = W * H * 3
    prev_z = 1.0
    for n in range(NF):
        raw = dec.stdout.read(fsz)
        if len(raw) < fsz:
            break
        t = n / FPS
        fr = Image.frombuffer("RGB", (W, H), raw, "raw", "RGB", 0, 1)
        z = zoom_at(t)
        # 4-frame ease between zoom levels
        z = prev_z + (z - prev_z) * 0.55 if abs(z - prev_z) > 0.002 else z
        prev_z = z
        if z > 1.001:
            cw, ch = W / z, H / z
            x0 = FACE[0] - FACE[0] / z
            y0 = FACE[1] - FACE[1] / z
            fr = fr.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))
        fr = fr.convert("RGBA")
        for e in E:
            r = element_frame(e, t)
            if r:
                img, s, a = r
                place(fr, img, e["cx"], e["cy"], s, e["rot"], a)
        cap, age = caption_at(groups, t)
        if cap is not None:
            dy = int(18 * (1 - ease_out(age / 0.18)))
            al = ease_out(age / 0.12)
            place(fr, cap, W / 2, CAP_Y + cap.height / 2 + dy, 1.0, 0, al)
        # progress bar
        d = ImageDraw.Draw(fr)
        d.rectangle((0, 0, int(W * t / DUR), 9), fill=ROSE + (255,))
        enc.stdin.write(fr.convert("RGB").tobytes())
        if n % 150 == 0:
            print(f"frame {n}/{NF}", flush=True)
    enc.stdin.close()
    enc.wait()
    dec.kill()          # base may hold a few frames past DUR; don't block on them
    dec.wait()


TIMELINE = []
ZOOMS = []

if __name__ == "__main__":
    tl = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
    TIMELINE[:] = tl["elements"]
    ZOOMS[:] = [tuple(z) for z in tl["zooms"]]
    base = os.path.join(WORK, "base.mp4")
    if not os.path.exists(base) or "--rebase" in sys.argv:
        base = stage_a()
    if "--still" in sys.argv:          # quick preview frames: --still t1,t2,...
        ts = [float(x) for x in sys.argv[sys.argv.index("--still") + 1].split(",")]
        groups = load_captions()
        E = build_elements()
        for t in ts:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", base,
                            "-frames:v", "1", os.path.join(WORK, "st.png")], check=True)
            fr = Image.open(os.path.join(WORK, "st.png")).convert("RGB")
            z = zoom_at(t)
            if z > 1.001:
                x0, y0 = FACE[0] - FACE[0] / z, FACE[1] - FACE[1] / z
                fr = fr.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + W / z, y0 + H / z))
            fr = fr.convert("RGBA")
            for e in E:
                r = element_frame(e, t)
                if r:
                    place(fr, r[0], e["cx"], e["cy"], r[1], e["rot"], r[2])
            cap, age = caption_at(groups, t)
            if cap is not None:
                place(fr, cap, W / 2, CAP_Y + cap.height / 2, 1.0, 0, 1.0)
            ImageDraw.Draw(fr).rectangle((0, 0, int(W * t / DUR), 9), fill=ROSE + (255,))
            fr.convert("RGB").save(os.path.join(WORK, f"still_{t:05.2f}.png"))
        sys.exit(0)
    render(base)
    print("done", OUT)
