#!/usr/bin/env python3
"""Build the Botox Instagram reel (1080x1920, ~28 s, silent, EN + KA captions).

Usage: python3 build.py <upload_dir> <work_dir> <output.mp4> [--rebase]
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SRC, WORK, OUT = sys.argv[1:4]
os.makedirs(WORK, exist_ok=True)
W, H, FPS = 1080, 1920, 30

ROSE = (214, 96, 128)      # accent
DARK = (30, 22, 34)
GREY = (80, 72, 84)
WHITE = (255, 255, 255)

F_EN_BLACK = "/usr/share/fonts/opentype/inter/Inter-Black.otf"
F_EN_XB = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_EN_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_EN_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
F_KA_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_KA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# short names for the uploaded clips (prefix of the upload file name)
CLIPS = {
    "squint": "f26c397d",     # crow's feet close-up (landscape)
    "brow": "8ce1c483",       # forehead lines close-up (landscape)
    "frown": "b777e38f",      # frown lines close-up (landscape)
    "chin": "9c8e9d13",       # lips / chin close-up (landscape)
    "relax": "d3c1fefe",      # forehead raise -> relaxed (landscape)
    "recline": "b897c558",    # patient on the chair, doctor
    "inject_back": "50b8f371",
    "lamp": "cb4c4aff",       # injecting forehead, warm lamp
    "close": "d69430fc",      # close injecting shot
    "profile": "913836e5",    # profile, smiles at camera at the end
    "smile": "ed45d44b",      # both smiling
    "consult": "63e2df39",    # consultation talk
    "wide": "2e056650",       # wide injection shot
}
LANDSCAPE = {"squint", "brow", "frown", "chin", "relax"}


def src(name):
    pre = CLIPS[name]
    return os.path.join(SRC, next(f for f in os.listdir(SRC) if f.startswith(pre)))


def font(path, size):
    return ImageFont.truetype(path, size)


def is_ka(ch):
    return 0x10A0 <= ord(ch) <= 0x10FF or ch in "„“"


def runs(text):
    out = []
    for ch in text:
        ka = is_ka(ch) or bool(out and out[-1][0] and ch in " -—–·0123456789")
        if out and out[-1][0] == ka:
            out[-1][1] += ch
        else:
            out.append([ka, ch])
    return out


def mixed_len(d, text, fe, fk):
    return sum(d.textlength(c, font=fk if k else fe) for k, c in runs(text))


def draw_mixed(d, x, y, text, fe, fk, fill):
    for k, c in runs(text):
        f = fk if k else fe
        d.text((x, y), c, font=f, fill=fill, anchor="lm")
        x += d.textlength(c, font=f)


# ---------------------------------------------------------------- shots
# (clip, source start, duration)
SHOTS = [
    # hook: fast wrinkle cuts
    ("squint", 0.2, 0.8),
    ("frown", 0.9, 0.8),
    ("brow", 0.7, 0.8),
    ("relax", 0.1, 0.9),
    # procedure
    ("consult", 2.2, 2.0),
    ("lamp", 3.0, 2.0),
    ("close", 0.2, 1.6),
    ("inject_back", 1.0, 1.6),
    ("wide", 3.2, 1.8),
    ("recline", 1.6, 1.6),
    # treatment areas
    ("brow", 2.0, 1.5),
    ("frown", 2.6, 1.5),
    ("squint", 2.4, 1.5),
    ("chin", 1.8, 1.5),
    # facts
    ("relax", 3.4, 2.0),
    ("profile", 0.0, 2.0),
    # outro
    ("smile", 0.0, 4.6),
]
FLASH_AT = {1, 2, 3, 4, 10, 14, 16}   # shot indices that start with a white flash


def render_shots():
    parts, t0 = [], 0.0
    for i, (clip, ss, d) in enumerate(SHOTS):
        out = os.path.join(WORK, f"shot{i:02d}.mp4")
        n = round(d * FPS)
        # punch-in: start 10% zoomed, settle to 1.0 in 0.25 s, then a slow push to +5%
        z = f"(1+0.10*max(0,1-t/0.25)+0.05*t/{d})"
        if clip in LANDSCAPE:
            # blurred full-bleed background + framed close-up so faces are not cropped
            vf = (
                "split[bg][fg];"
                "[bg]scale=-2:1920,crop=1080:1920,gblur=sigma=40,eq=brightness=-0.06:saturation=0.8[b];"
                f"[fg]scale=w='trunc(1700*{z}/2)*2':h=-2:eval=frame:flags=bicubic,"
                "crop=1080:956,unsharp=5:5:0.6[f];"
                "[b][f]overlay=0:300"
            )
        else:
            vf = (
                f"scale=w='trunc(1080*{z}/2)*2':h=-2:eval=frame:flags=bicubic,"
                "crop=1080:1920"
            )
        vf += ",eq=contrast=1.05:saturation=1.05"
        if i in FLASH_AT:
            vf += ",fade=t=in:st=0:d=0.15:color=white"
        vf += ",format=yuv420p"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-t", str(d + 0.1),
             "-i", src(clip), "-an", "-filter_complex", vf, "-r", str(FPS),
             "-frames:v", str(n), "-c:v", "libx264", "-crf", "15", "-preset", "fast", out],
            check=True)
        parts.append(out)
        t0 += d
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    base = os.path.join(WORK, "base.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", base], check=True)
    return base


def shot_start(i):
    return sum(d for _, _, d in SHOTS[:i])


TOTAL = shot_start(len(SHOTS))


# ---------------------------------------------------------------- text art
def save(im, name):
    p = os.path.join(WORK, name + ".png")
    im.save(p)
    return p


def big_text(en, ka, cy=1520, name="big", size=130):
    """Huge white headline with shadow and a rose Georgian pill under it."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fe = font(F_EN_BLACK, size)
    lines = en.split("\n")
    while max(d.textlength(l, font=fe) for l in lines) > 980:
        size -= 6
        fe = font(F_EN_BLACK, size)
    lh = int(size * 1.05)
    top = cy - lh * (len(lines) - 1)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for k, l in enumerate(lines):
        sd.text((W / 2, top + k * lh + 6), l, font=fe, fill=(0, 0, 0, 170), anchor="mm")
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    for k, l in enumerate(lines):
        d.text((W / 2, top + k * lh), l, font=fe, fill=WHITE, anchor="mm")
    fk = font(F_KA_BOLD, 48)
    fe2 = font(F_EN_BOLD, 48)
    tw = mixed_len(d, ka, fe2, fk)
    y = cy + size * 0.55 + 18
    d.rounded_rectangle((W / 2 - tw / 2 - 32, y, W / 2 + tw / 2 + 32, y + 84), 42, fill=ROSE + (240,))
    draw_mixed(d, W / 2 - tw / 2, y + 42, ka, fe2, fk, WHITE)
    return save(im, name)


def caption(en, ka, y=1430, name="cap", pill=None):
    """Lower-third: white rounded card with EN headline + KA line, optional pill above."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fe = font(F_EN_XB, 62)
    fk = font(F_KA_BOLD, 38)
    w = max(d.textlength(en, font=fe), d.textlength(ka, font=fk)) + 100
    w = min(max(w, 560), 980)
    x0 = (W - w) / 2
    h = 190
    if pill:
        fp, fpk = font(F_EN_BOLD, 28), font(F_KA_BOLD, 26)
        pw = mixed_len(d, pill, fp, fpk) + 44
        d.rounded_rectangle((W / 2 - pw / 2, y - 70, W / 2 + pw / 2, y - 14), 28, fill=ROSE)
        draw_mixed(d, W / 2 - pw / 2 + 22, y - 42, pill, fp, fpk, WHITE)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0, y + 10, x0 + w, y + h + 10), 40, fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(20)))
    d = ImageDraw.Draw(im)
    if pill:  # redraw pill over shadow
        d.rounded_rectangle((W / 2 - pw / 2, y - 70, W / 2 + pw / 2, y - 14), 28, fill=ROSE)
        draw_mixed(d, W / 2 - pw / 2 + 22, y - 42, pill, fp, fpk, WHITE)
    d.rounded_rectangle((x0, y, x0 + w, y + h), 40, fill=(255, 255, 255, 242))
    d.text((W / 2, y + 68), en, font=fe, fill=DARK, anchor="mm")
    d.text((W / 2, y + 140), ka, font=fk, fill=ROSE, anchor="mm")
    return save(im, name)


def area_tag(en, ka, idx, name):
    """Treatment-area label for the framed close-ups (sits under the frame)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fp = font(F_EN_BOLD, 30)
    t = f"TREATMENT AREA {idx}/4  ·  ზონა {idx}/4"
    fpk = font(F_KA_BOLD, 28)
    pw = mixed_len(d, t, fp, fpk) + 48
    d.rounded_rectangle((W / 2 - pw / 2, 196, W / 2 + pw / 2, 258), 31, fill=ROSE)
    draw_mixed(d, W / 2 - pw / 2 + 24, 227, t, fp, fpk, WHITE)
    fe = font(F_EN_BLACK, 96)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((W / 2, 1380), en, font=fe, fill=(0, 0, 0, 170), anchor="mm")
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    d.text((W / 2, 1374), en, font=fe, fill=WHITE, anchor="mm")
    fk = font(F_KA_BOLD, 50)
    tw = d.textlength(ka, font=fk)
    d.rounded_rectangle((W / 2 - tw / 2 - 32, 1450, W / 2 + tw / 2 + 32, 1536), 43, fill=(255, 255, 255, 240))
    d.text((W / 2, 1493), ka, font=fk, fill=ROSE, anchor="mm")
    return save(im, name)


def brand_top():
    """Small persistent BOTOX · ბოტოქსი mark at the top."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fe, fk = font(F_EN_XB, 30), font(F_KA_BOLD, 28)
    t = "BOTOX  ·  ბოტოქსი"
    tw = mixed_len(d, t, fe, fk)
    d.rounded_rectangle((W / 2 - tw / 2 - 26, 110, W / 2 + tw / 2 + 26, 168), 29, fill=(255, 255, 255, 215))
    draw_mixed(d, W / 2 - tw / 2, 139, t, fe, fk, DARK)
    return save(im, "brand")


def end_card():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(H):  # darker towards the bottom for legibility
        a = int(60 + 150 * max(0, (y - 500) / (H - 500)))
        gd.line([(0, y), (W, y)], fill=(25, 12, 22, a))
    im = Image.alpha_composite(im, grad)
    d = ImageDraw.Draw(im)
    cy = 1080
    d.text((W / 2, cy), "Book your", font=font(F_EN_XB, 64), fill=WHITE, anchor="mm")
    fe = font(F_EN_BLACK, 132)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((W / 2, cy + 120), "consultation", font=fe, fill=ROSE + (255,), anchor="mm")
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(28)))
    d = ImageDraw.Draw(im)
    d.text((W / 2, cy + 120), "consultation", font=fe, fill=WHITE, anchor="mm")
    fk = font(F_KA_BOLD, 50)
    ka = "ჩაეწერეთ კონსულტაციაზე"
    tw = d.textlength(ka, font=fk)
    y = cy + 210
    d.rounded_rectangle((W / 2 - tw / 2 - 34, y, W / 2 + tw / 2 + 34, y + 88), 44, fill=ROSE)
    d.text((W / 2, y + 44), ka, font=fk, fill=WHITE, anchor="mm")
    d.line([(W / 2 - 60, y + 150), (W / 2 + 60, y + 150)], fill=WHITE, width=4)
    d.text((W / 2, y + 220), "Dr. Luka Chigogidze", font=font(F_EN_BLACK, 60), fill=WHITE, anchor="mm")
    d.text((W / 2, y + 290), "ექიმი ლუკა ჩიგოგიძე", font=font(F_KA_BOLD, 40), fill=WHITE, anchor="mm")
    d.text((W / 2, 1800), "Individual results may vary  ·  შედეგი ინდივიდუალურია",
           font=font(F_KA, 24), fill=(225, 210, 218), anchor="mm")
    return save(im, "end")


# ---------------------------------------------------------------- timeline
def overlays():
    O = []  # (png, start, end, slide)
    s = shot_start
    O.append((big_text("Wrinkles?", "ნაოჭები გაწუხებთ?", name="hook0"), 0.0, s(2), False))
    O.append((big_text("Let's smooth\nthem out.", "მოდით, გავასწოროთ", name="hook1"), s(2), s(4), False))

    O.append((brand_top(), s(4), s(16), False))
    O.append((caption("Personal consultation", "ინდივიდუალური კონსულტაცია", name="c0",
                      pill="STEP 1  ·  ნაბიჯი 1"), s(4), s(5), True))
    O.append((caption("Precise mapping", "ზუსტი დაგეგმვა და მარკირება", name="c1",
                      pill="STEP 2  ·  ნაბიჯი 2"), s(5), s(7), True))
    O.append((caption("Micro-injections", "მიკროინექციები", name="c2",
                      pill="STEP 3  ·  ნაბიჯი 3"), s(7), s(9), True))
    O.append((caption("Quick · ~15 minutes", "სწრაფი · დაახლ. 15 წუთი", name="c3"), s(9), s(10), True))

    areas = [("Forehead lines", "შუბლის ნაოჭები"), ("Frown lines", "წარბშორისი ნაოჭები"),
             ("Crow's feet", "„ყვავის ფეხები“"), ("Chin", "ნიკაპი")]
    for k, (en, ka) in enumerate(areas):
        O.append((area_tag(en, ka, k + 1, f"area{k}"), s(10 + k), s(11 + k), True))

    O.append((caption("Visible in 3–14 days", "შედეგი 3–14 დღეში", name="f0",
                      pill="RESULTS  ·  შედეგი"), s(14), s(15), True))
    O.append((caption("Lasts 3–4 months", "ეფექტი გრძელდება 3–4 თვე", name="f1",
                      pill="NATURAL LOOK  ·  ბუნებრივი იერი"), s(15), s(16), True))

    O.append((caption("Fresh. Rested. Natural.", "ახალი. დასვენებული. ბუნებრივი.", name="o0",
                      y=1500), s(16), s(16) + 1.5, True))
    O.append((end_card(), s(16) + 1.6, TOTAL, False))
    return O


def compose(base, O):
    args = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for png, s, e, _ in O:
        args += ["-loop", "1", "-t", f"{e:.2f}", "-i", png]
    fc, last = [], "0:v"
    for k, (png, s, e, slide) in enumerate(O, start=1):
        fi = 0.12
        fo = min(0.12, (e - s) / 4)
        fade_out = "" if e >= TOTAL - 0.01 else f",fade=t=out:st={e - fo:.2f}:d={fo:.2f}:alpha=1"
        fc.append(f"[{k}:v]format=rgba,fade=t=in:st={s:.2f}:d={fi}:alpha=1{fade_out}[o{k}]")
        y = f"'if(lt(t,{s + 0.22:.2f}),60*({s + 0.22:.2f}-t)/0.22,0)'" if slide else "0"
        fc.append(f"[{last}][o{k}]overlay=x=0:y={y}:enable='between(t,{s:.2f},{e:.2f})'[v{k}]")
        last = f"v{k}"
    fc.append(f"[{last}]format=yuv420p[out]")
    args += ["-filter_complex", ";".join(fc), "-map", "[out]", "-t", f"{TOTAL:.2f}",
             "-r", str(FPS), "-c:v", "libx264", "-crf", "17", "-preset", "slow",
             "-profile:v", "high", "-movflags", "+faststart", "-an", OUT]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    print("total", TOTAL)
    O = overlays()
    base = os.path.join(WORK, "base.mp4")
    if not os.path.exists(base) or "--rebase" in sys.argv:
        base = render_shots()
    compose(base, O)
    print("done", OUT)
