#!/usr/bin/env python3
"""Build the "3 Danger Zones for Fillers" reel (1080x1920, 30 fps, KA + EN captions).

Usage: python3 build.py <base.mov> <work_dir> <output.mp4>

<base.mov> is the source already tone-mapped HDR->SDR, 30 fps and stabilised
(see README.md). All timings in edit.py are in SOURCE seconds; this script
removes the cut gaps and remaps every caption / overlay onto the output timeline.
"""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from edit import CAPTIONS, CUTS, EN_LINES, HIGHLIGHT, OVERLAYS, DANGER

BASE, WORK, OUT = sys.argv[1:4]
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
os.makedirs(WORK, exist_ok=True)
W, H, FPS = 1080, 1920, 30

F_KA_BLACK = os.path.join(FONTS, "NotoSansGeorgian-Black.ttf")
F_KA_XB = os.path.join(FONTS, "NotoSansGeorgian-ExtraBold.ttf")
F_KA_SB = os.path.join(FONTS, "NotoSansGeorgian-SemiBold.ttf")
F_EN_BLACK = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"
F_EN_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
F_EN_SB = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"

RED = (255, 59, 48)
YELLOW = (255, 214, 10)
WHITE = (255, 255, 255)
CARD = (12, 18, 30, 205)


# ------------------------------------------------------------ timeline remap
def build_map():
    """List of (src_start, src_end, out_start) for each kept piece."""
    m, t = [], 0.0
    for s, e in CUTS:
        m.append((s, e, t))
        t += e - s
    return m, t


MAP, TOTAL = build_map()


def remap(t, clamp="start"):
    """Source time -> output time. Times inside a cut snap to the nearest kept edge."""
    for i, (s, e, o) in enumerate(MAP):
        if s <= t <= e:
            return o + (t - s)
        if t < s:
            return o  # inside the gap before piece i -> start of piece i
    return TOTAL


# ------------------------------------------------------------ ASS captions
def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def bgr(rgb):
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}&"


def caption_ass(path):
    ka_size, en_size = 74, 40
    ka_y, en_y = 1505, 1590
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KA,Noto Sans Georgian Black,{ka_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,6,3,2,60,60,0,1
Style: EN,Inter SemiBold,{en_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,3.5,2,2,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []

    def word_color(w, active):
        key = w.strip(".,?!:;—–-\"„“").lower()
        if any(key.startswith(d) for d in DANGER):
            return RED
        if active:
            return YELLOW
        return WHITE

    for cap in CAPTIONS:
        words = cap["words"]  # list of (text, src_start)
        end_src = cap["end"]
        o_end = remap(end_src)
        o_starts = [remap(t) for _, t in words]
        for i in range(len(words)):
            a = o_starts[i]
            b = o_starts[i + 1] if i + 1 < len(words) else o_end
            if b - a < 0.02:
                continue
            parts = []
            for j, (w, _) in enumerate(words):
                c = word_color(w, j == i)
                parts.append("{\\c" + bgr(c) + "}" + w)
            pop = ""
            if i == 0:
                pop = "\\fscx86\\fscy86\\t(0,110,\\fscx100\\fscy100)"
            text = "{\\pos(%d,%d)%s}" % (W // 2, ka_y, pop) + " ".join(parts)
            ev.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},KA,,0,0,0,,{text}")

    for s, e, text in EN_LINES:
        a, b = remap(s), remap(e)
        if b - a < 0.05:
            continue
        ev.append(
            f"Dialogue: 0,{ass_time(a)},{ass_time(b)},EN,,0,0,0,,"
            "{\\pos(%d,%d)\\fad(80,80)}%s" % (W // 2, en_y, text)
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")


# ------------------------------------------------------------ PNG overlays
def font(p, s):
    return ImageFont.truetype(p, s)


def shadowed(img, radius=18, alpha=150):
    """Soft drop shadow under everything drawn on an RGBA layer."""
    a = img.split()[3].point(lambda v: min(alpha, v))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(radius)))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 8))
    out.alpha_composite(img)
    return out


def centered(d, y, text, f, fill, anchor="mm"):
    d.text((W // 2, y), text, font=f, fill=fill, anchor=anchor)


def hook_card(path, ka, en_pre, en_hot):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fk = font(F_KA_BLACK, 64)
    fe = font(F_EN_BLACK, 54)
    lines = ka
    pad, gap = 44, 14
    widths = [d.textlength(t, font=fk) for t in lines]
    en_w = d.textlength(en_pre + " ", font=fe) + d.textlength(en_hot, font=fe)
    bw = int(max(widths + [en_w]) + pad * 2)
    lh = 86
    bh = pad * 2 + lh * len(lines) + 70 + gap
    x0, y0 = (W - bw) // 2, 250
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 34, fill=CARD)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + 12), 6, fill=RED)
    y = y0 + pad + lh // 2 + 6
    for t in lines:
        # red for the danger word inside the KA line
        xs = W // 2 - d.textlength(t, font=fk) / 2
        for k, chunk in enumerate(t.split(" ")):
            col = RED if any(chunk.startswith(dw) for dw in DANGER) else WHITE
            d.text((xs, y), chunk, font=fk, fill=col, anchor="lm")
            xs += d.textlength(chunk + " ", font=fk)
        y += lh
    y += gap + 20
    xs = W // 2 - en_w / 2
    d.text((xs, y), en_pre + " ", font=fe, fill=(225, 230, 238), anchor="lm")
    xs += d.textlength(en_pre + " ", font=fe)
    d.text((xs, y), en_hot, font=fe, fill=RED, anchor="lm")
    shadowed(img).save(path)


def zone_label(path, num, ka, en):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fn = font(F_EN_BLACK, 40)
    fk = font(F_KA_BLACK, 54)
    fe = font(F_EN_SB, 34)
    badge = 84
    tw = max(d.textlength(ka, font=fk), d.textlength(en, font=fe))
    bw = int(badge + 30 + tw + 50)
    bh = 128
    x0, y0 = (W - bw) // 2, 250
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 30, fill=CARD)
    cx, cy = x0 + 22 + badge // 2, y0 + bh // 2
    d.ellipse((cx - badge // 2, cy - badge // 2, cx + badge // 2, cy + badge // 2), fill=RED)
    d.text((cx, cy + 1), str(num), font=fn, fill=WHITE, anchor="mm")
    tx = x0 + 22 + badge + 26
    d.text((tx, y0 + 50), ka, font=fk, fill=WHITE, anchor="lm")
    d.text((tx, y0 + 100), en, font=fe, fill=(200, 208, 220), anchor="lm")
    shadowed(img).save(path)


def warning_card(path, title_ka, title_en, items, shown):
    """items: list of (ka, en); `shown` = how many items are visible (build-up)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ft = font(F_KA_BLACK, 46)
    fte = font(F_EN_BOLD, 28)
    fk = font(F_KA_XB, 38)
    fe = font(F_EN_SB, 27)
    pad = 36
    bw = 900
    row = 92
    bh = pad + 58 + 40 + 14 + row * len(items) + pad - 10
    x0, y0 = (W - bw) // 2, 215
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 32, fill=CARD)
    d.rounded_rectangle((x0, y0, x0 + 12, y0 + bh), 6, fill=RED)
    tx = x0 + pad + 14
    d.text((tx, y0 + pad + 24), title_ka, font=ft, fill=RED, anchor="lm")
    d.text((tx, y0 + pad + 72), title_en, font=fte, fill=(200, 208, 220), anchor="lm")
    y = y0 + pad + 58 + 40 + 14 + 30
    for i, (ka, en) in enumerate(items):
        if i >= shown:
            break
        d.ellipse((tx, y - 9, tx + 18, y + 9), fill=RED)
        d.text((tx + 36, y), ka, font=fk, fill=WHITE, anchor="lm")
        d.text((tx + 36, y + 38), en, font=fe, fill=(190, 198, 210), anchor="lm")
        y += row
    shadowed(img).save(path)


def end_card(path, handle):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fk = font(F_KA_BLACK, 52)
    fe = font(F_EN_SB, 34)
    fh = font(F_EN_BLACK, 66)
    bw, bh = 860, 330
    x0, y0 = (W - bw) // 2, 250
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), 36, fill=CARD)
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + 12), 6, fill=RED)
    centered(d, y0 + 82, "შეინახე და გაუზიარე", fk, WHITE)
    centered(d, y0 + 136, "Save & share with someone booking fillers", fe, (200, 208, 220))
    centered(d, y0 + 240, handle, fh, YELLOW)
    shadowed(img).save(path)


def make_overlays():
    """Render PNGs; return list of (png, out_start, out_end)."""
    res = []
    for i, ov in enumerate(OVERLAYS):
        p = os.path.join(WORK, f"ov_{i:02d}.png")
        kind = ov["kind"]
        if kind == "hook":
            hook_card(p, ov["ka"], ov["en_pre"], ov["en_hot"])
        elif kind == "zone":
            zone_label(p, ov["num"], ov["ka"], ov["en"])
        elif kind == "warn":
            warning_card(p, ov["title_ka"], ov["title_en"], ov["items"], ov["shown"])
        elif kind == "end":
            end_card(p, ov["handle"])
        a = remap(ov["start"])
        b = TOTAL if ov["end"] is None else remap(ov["end"])
        res.append((p, a, b, ov.get("fade", True)))
    return res


# ------------------------------------------------------------ render
def run(cmd):
    print(" ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True)


def main():
    ass = os.path.join(WORK, "captions.ass")
    caption_ass(ass)
    ovs = make_overlays()

    # 1) cut + concat (video and audio), tiny audio fades at each join to avoid clicks
    fc, vs, as_ = [], [], []
    for i, (s, e, _) in enumerate(MAP):
        d = e - s
        fc.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        fc.append(
            f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.015):.3f}:d=0.015[a{i}]"
        )
        vs.append(f"[v{i}][a{i}]")
    fc.append("".join(vs) + f"concat=n={len(MAP)}:v=1:a=1[vc][ac]")

    # 2) overlays
    last = "vc"
    for k, (p, a, b, fade) in enumerate(ovs):
        idx = k + 1
        fd = 0.18 if fade else 0.0
        chain = f"[{idx}:v]format=rgba"
        if fade:
            chain += (f",fade=t=in:st={a:.3f}:d={fd}:alpha=1"
                      f",fade=t=out:st={max(a, b - fd):.3f}:d={fd}:alpha=1")
        chain += f"[o{k}]"
        fc.append(chain)
        fc.append(f"[{last}][o{k}]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[w{k}]")
        last = f"w{k}"

    # 3) captions
    fc.append(f"[{last}]ass={ass}:fontsdir={FONTS},format=yuv420p[vout]")

    # 4) voice clean-up + loudness for Instagram (-14 LUFS)
    fc.append(
        "[ac]highpass=f=85,afftdn=nf=-50:nr=8,"
        "equalizer=f=3500:t=q:w=1.2:g=2,"
        "acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=4,"
        "loudnorm=I=-14:TP=-1.5:LRA=9,aresample=48000[aout]"
    )

    cmd = ["ffmpeg", "-v", "error", "-stats", "-y", "-i", BASE]
    for p, *_ in ovs:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{TOTAL:.3f}", "-i", p]
    cmd += [
        "-filter_complex", ";".join(fc),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-t", f"{TOTAL:.3f}", OUT,
    ]
    run(cmd)
    print(f"done: {OUT}  ({TOTAL:.1f}s)")


if __name__ == "__main__":
    main()
