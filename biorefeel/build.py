#!/usr/bin/env python3
"""Build the BioReFeel Instagram reel (1080x1920, 45 s, silent, EN + KA text).

Usage: python3 build.py <proxy_dir> <work_dir> <output.mp4>
<proxy_dir> holds IMG_99xx.mp4 clips already scaled to 1080x1920 @ 30 fps.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROXY, WORK, OUT = sys.argv[1:4]
os.makedirs(WORK, exist_ok=True)
W, H, FPS = 1080, 1920, 30

TEAL = (0, 158, 175)
DARK = (10, 38, 44)
GREY = (70, 88, 92)
WHITE = (255, 255, 255)

F_EN_BLACK = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_EN_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_EN_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
F_KA_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_KA = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def runs(text):
    """Split text into (is_georgian, chunk) runs so each script gets a font with its glyphs."""
    out = []
    for ch in text:
        ka = 0x10A0 <= ord(ch) <= 0x10FF or (out and out[-1][0] and ch in " -—")
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
    # hook
    ("IMG_9939", 0.3, 1.5),
    ("IMG_9943", 0.3, 1.5),
    ("IMG_9934", 1.0, 1.5),
    ("IMG_9932", 0.5, 1.5),
    # intro
    ("IMG_9921", 0.3, 2.4),
    ("IMG_9924", 3.4, 2.3),
    # concept
    ("IMG_9930", 0.5, 1.8),
    ("IMG_9940", 0.3, 2.0),
    # ingredients
    ("IMG_9939", 2.2, 2.2),
    ("IMG_9938", 0.5, 2.1),
    ("IMG_9943", 2.0, 2.3),
    ("IMG_9936", 0.5, 2.0),
    ("IMG_9934", 4.0, 2.3),
    ("IMG_9935", 0.5, 2.0),
    # results
    ("IMG_9932", 3.5, 2.0),
    ("IMG_9930", 4.0, 2.0),
    ("IMG_9934", 7.0, 2.0),
    ("IMG_9938", 4.0, 2.0),
    # natural
    ("IMG_9936", 3.5, 2.0),
    ("IMG_9930", 7.5, 2.0),
    # outro
    ("IMG_9940", 3.0, 2.0),
    ("IMG_9942", 0.3, 3.6),
]


def render_shots():
    parts = []
    for i, (clip, ss, d) in enumerate(SHOTS):
        out = os.path.join(WORK, f"shot{i:02d}.mp4")
        # gentle push-in, light grade and a soft bloom for the "glow" look
        vf = (
            f"scale=w='trunc(1080*(1+0.06*t/{d})/2)*2':h=-2:eval=frame:flags=bicubic,"
            f"crop=1080:1920,"
            "eq=contrast=1.04:saturation=1.08:brightness=0.01,"
            "split[a][b];[b]gblur=sigma=28[g];[a][g]blend=all_mode=screen:all_opacity=0.18,"
            "format=yuv420p"
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-t", str(d),
             "-i", os.path.join(PROXY, clip + ".mp4"), "-an",
             "-filter_complex", vf, "-r", str(FPS), "-frames:v", str(round(d * FPS)),
             "-c:v", "libx264", "-crf", "15", "-preset", "fast", out],
            check=True)
        parts.append(out)
    lst = os.path.join(WORK, "list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
    base = os.path.join(WORK, "base.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", base], check=True)
    return base


# ---------------------------------------------------------------- text art
def wrap(draw, text, fnt, maxw):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def card(rows, bottom=1500, left=60, width=860, pad=44, name="card"):
    """rows: list of (kind, text) drawn top-to-bottom on a white rounded card.
    kinds: pill, title, title_ka, body, body_ka, gap, tag"""
    styles = {
        "title": (font(F_EN_BLACK, 66), DARK, 10),
        "title_ka": (font(F_KA_BOLD, 40), TEAL, 18),
        "body": (font(F_EN_MED, 36), GREY, 8),
        "body_ka": (font(F_KA, 31), GREY, 14),
    }
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    inner = width - 2 * pad
    layout, hgt = [], pad
    for kind, text in rows:
        if kind == "gap":
            layout.append((kind, None, hgt))
            hgt += text
        elif kind in ("pill", "tag"):
            f = font(F_EN_BOLD, 26)
            layout.append((kind, (text, f), hgt))
            hgt += 52 + 18
        else:
            f, col, after = styles[kind]
            for ln in wrap(tmp, text, f, inner):
                bb = tmp.textbbox((0, 0), "Ag" if kind in ("title", "body") else "აგ", font=f)
                lh = int((bb[3] - bb[1]) * 1.25)
                layout.append((kind, (ln, f, col), hgt))
                hgt += lh
            hgt += after
    hgt += pad - 14
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top = bottom - hgt
    # shadow
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (left, top + 10, left + width, bottom + 10), 38, fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((left, top, left + width, bottom), 38, fill=(255, 255, 255, 240))
    d.rounded_rectangle((left, top + 40, left + 10, bottom - 40), 5, fill=TEAL)  # accent bar
    x = left + pad
    for kind, data, y in layout:
        y += top
        if kind in ("pill", "tag"):
            text, f = data
            fk = font(F_KA_BOLD, 24)
            tw = mixed_len(d, text, f, fk)
            fill, tc = (TEAL, WHITE) if kind == "pill" else ((230, 246, 248, 255), TEAL)
            d.rounded_rectangle((x, y, x + tw + 40, y + 52), 26, fill=fill)
            draw_mixed(d, x + 20, y + 26, text, f, fk, tc)
        elif kind != "gap":
            text, f, col = data
            d.text((x, y), text, font=f, fill=col)
    p = os.path.join(WORK, name + ".png")
    im.save(p)
    return p


def glow_text(en, ka, cy=1180, name="hook", size=150):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fe = font(F_EN_BLACK, size)
    d = ImageDraw.Draw(im)
    while d.textlength(en, font=fe) > 980:
        size -= 6
        fe = font(F_EN_BLACK, size)
    # glow layer
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((W / 2, cy), en, font=fe, fill=(120, 230, 240, 255), anchor="mm")
    g = g.filter(ImageFilter.GaussianBlur(26))
    im = Image.alpha_composite(im, g)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((W / 2, cy + 6), en, font=fe, fill=(0, 0, 0, 130), anchor="mm")
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(im)
    d.text((W / 2, cy), en, font=fe, fill=WHITE, anchor="mm")
    fk = font(F_KA_BOLD, 50)
    tw = d.textlength(ka, font=fk)
    y = cy + size * 0.62 + 20
    d.rounded_rectangle((W / 2 - tw / 2 - 30, y, W / 2 + tw / 2 + 30, y + 80), 40, fill=TEAL + (235,))
    d.text((W / 2, y + 40), ka, font=fk, fill=WHITE, anchor="mm")
    p = os.path.join(WORK, name + ".png")
    im.save(p)
    return p


def bullet(i, en, ka, top=1060, name="b"):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y = top + i * 112
    d.rounded_rectangle((60, y, 920, y + 96), 48, fill=(255, 255, 255, 240))
    d.ellipse((76, y + 16, 140, y + 80), fill=TEAL)
    d.line([(94, y + 49), (105, y + 60), (124, y + 37)], fill=WHITE, width=7, joint="curve")
    d.text((164, y + 14), en, font=font(F_EN_BLACK, 40), fill=DARK)
    d.text((164, y + 58), ka, font=font(F_KA_BOLD, 27), fill=TEAL)
    p = os.path.join(WORK, f"{name}{i}.png")
    im.save(p)
    return p


def header(en, ka, y=930, name="hdr"):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(F_EN_BOLD, 30)
    t = f"{en}  ·  {ka}"
    fk = font(F_KA_BOLD, 30)
    w1 = d.textlength(en + "  ·  ", font=f)
    w2 = d.textlength(ka, font=fk)
    d.rounded_rectangle((60, y, 60 + w1 + w2 + 48, y + 64), 32, fill=TEAL)
    d.text((84, y + 32), en + "  ·  ", font=f, fill=WHITE, anchor="lm")
    d.text((84 + w1, y + 32), ka, font=fk, fill=WHITE, anchor="lm")
    p = os.path.join(WORK, name + ".png")
    im.save(p)
    return p


def end_card():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # dark teal wash for legibility
    wash = Image.new("RGBA", (W, H), (4, 30, 36, 150))
    im = Image.alpha_composite(im, wash)
    d = ImageDraw.Draw(im)
    cy = 760
    fe = font(F_EN_BLACK, 120)
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((W / 2, cy), "BioReFeel®", font=fe, fill=(90, 220, 235, 255), anchor="mm")
    im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(im)
    d.text((W / 2, cy), "BioReFeel®", font=fe, fill=WHITE, anchor="mm")
    d.text((W / 2, cy + 105), "Skin quality, redefined", font=font(F_EN_MED, 40),
           fill=(200, 240, 245), anchor="mm")
    d.text((W / 2, cy + 160), "კანის ხარისხი — ახლებურად", font=font(F_KA, 32),
           fill=(200, 240, 245), anchor="mm")
    d.line([(W / 2 - 60, cy + 235), (W / 2 + 60, cy + 235)], fill=TEAL, width=5)
    d.text((W / 2, cy + 310), "Dr. Luka Chigogidze", font=font(F_EN_BLACK, 62),
           fill=WHITE, anchor="mm")
    d.text((W / 2, cy + 380), "ექიმი ლუკა ჩიგოგიძე", font=font(F_KA_BOLD, 40),
           fill=WHITE, anchor="mm")
    d.text((W / 2, 1560), "Individual results may vary · შედეგი ინდივიდუალურია",
           font=font(F_KA, 24), fill=(180, 210, 214), anchor="mm")
    p = os.path.join(WORK, "end.png")
    im.save(p)
    return p


# ---------------------------------------------------------------- timeline
def overlays():
    O = []  # (png, start, end, slide)
    hook = [("GLOW", "ბზინვარება"), ("HYDRATION", "დატენიანება"),
            ("REJUVENATION", "გაახალგაზრდავება"), ("NO VOLUME.", "მოცულობის გარეშე")]
    for i, (en, ka) in enumerate(hook):
        O.append((glow_text(en, ka, name=f"hook{i}"), i * 1.5 + 0.05, i * 1.5 + 1.5, False))

    O.append((card([
        ("pill", "NEW  ·  სიახლე"),
        ("title", "Meet BioReFeel®"),
        ("title_ka", "გაიცანით BioReFeel®"),
        ("body", "Injectable skin restructurant by CMed Aesthetics, makers of BioRePeel®"),
        ("body_ka", "ინექციური კანის რესტრუქტურანტი BioRePeel®-ის მწარმოებლისგან"),
    ], name="intro"), 6.1, 10.6, True))

    O.append((card([
        ("title", "Improves skin quality"),
        ("title_ka", "აუმჯობესებს კანის ხარისხს"),
        ("body", "Not facial volume. Hydration, elasticity and glow."),
        ("body_ka", "და არა სახის მოცულობას — დატენიანება, ელასტიურობა, ბზინვარება"),
    ], name="concept"), 10.8, 14.4, True))

    O.append((card([
        ("pill", "01  ·  INGREDIENT"),
        ("title", "Hyaluronic Acid"),
        ("title_ka", "ჰიალურონის მჟავა"),
        ("body", "Bio-fermented, multiple molecular weights for hydration at every skin depth"),
        ("body_ka", "ბიოფერმენტირებული, სხვადასხვა მოლეკულური წონის — დატენიანება კანის ყველა შრეში"),
        ("tag", "80 mg / 2.4 mL"),
    ], name="ha"), 14.6, 18.7, True))

    O.append((card([
        ("pill", "02  ·  INGREDIENT"),
        ("title", "Amino Acids"),
        ("title_ka", "ამინომჟავები"),
        ("body", "Glycine · Proline · Hydroxyproline + functional amino acids"),
        ("body_ka", "გლიცინი · პროლინი · ჰიდროქსიპროლინი + ფუნქციური ამინომჟავები"),
        ("tag", "SKIN STRUCTURE  ·  კანის სტრუქტურა"),
    ], name="aa"), 18.9, 23.0, True))

    O.append((card([
        ("pill", "03  ·  INGREDIENT"),
        ("title", "Succinic Acid"),
        ("title_ka", "ქარვის მჟავა"),
        ("body", "Supports cellular energy and skin revitalization"),
        ("body_ka", "უჯრედული ენერგია და კანის რევიტალიზაცია"),
    ], name="sa"), 23.2, 27.3, True))

    O.append((header("RESULTS", "შედეგი"), 27.5, 35.3, True))
    bl = [("Deep hydration", "ღრმა დატენიანება"), ("Elasticity", "ელასტიურობა"),
          ("Natural glow", "ბუნებრივი ბზინვარება"), ("Rejuvenated skin", "გაახალგაზრდავებული კანი")]
    for i, (en, ka) in enumerate(bl):
        O.append((bullet(i, en, ka), 28.0 + i * 1.4, 35.3, True))

    O.append((card([
        ("title", "Natural results"),
        ("title_ka", "ბუნებრივი შედეგი"),
        ("body", "Fresh, hydrated skin with no added volume"),
        ("body_ka", "ახალი, დატენიანებული კანი — მოცულობის დამატების გარეშე"),
    ], name="natural"), 35.5, 39.3, True))

    O.append((card([
        ("pill", "PERFORMED BY  ·  პროცედურას ატარებს"),
        ("title", "Dr. Luka Chigogidze"),
        ("title_ka", "ექიმი ლუკა ჩიგოგიძე"),
    ], name="doctor"), 39.5, 41.4, True))

    O.append((end_card(), 41.45, 45.0, False))
    return O


def compose(base, O):
    args = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for png, s, e, _ in O:
        args += ["-loop", "1", "-t", f"{e:.2f}", "-i", png]
    fc, last = [], "0:v"
    for k, (png, s, e, slide) in enumerate(O, start=1):
        fo = min(0.18, (e - s) / 4)
        fc.append(
            f"[{k}:v]format=rgba,fade=t=in:st={s:.2f}:d=0.18:alpha=1,"
            f"fade=t=out:st={e - fo:.2f}:d={fo:.2f}:alpha=1[o{k}]")
        y = f"'if(lt(t,{s + 0.3:.2f}),40*({s + 0.3:.2f}-t)/0.3,0)'" if slide else "0"
        fc.append(f"[{last}][o{k}]overlay=x=0:y={y}:enable='between(t,{s:.2f},{e:.2f})'[v{k}]")
        last = f"v{k}"
    fc.append(f"[{last}]format=yuv420p[out]")
    args += ["-filter_complex", ";".join(fc), "-map", "[out]", "-t", "45", "-r", str(FPS),
             "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-profile:v", "high",
             "-movflags", "+faststart", "-an", OUT]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    print("total", sum(d for _, _, d in SHOTS))
    O = overlays()
    base = os.path.join(WORK, "base.mp4")
    if not os.path.exists(base) or "--rebase" in sys.argv:
        base = render_shots()
    compose(base, O)
    print("done", OUT)
