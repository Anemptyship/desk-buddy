"""2D graphics for the film: cards, chips, titles, key presses, desk-map overlays. English only."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FONT_DIR = "/usr/share/fonts/opentype/inter/"

TIER = {
    "fyi": ("FYI", (150, 210, 255)),
    "needs_you": ("NEEDS YOU", (255, 205, 110)),
    "urgent": ("URGENT", (255, 128, 112)),
    "wellbeing": ("WELLBEING", (140, 236, 200)),
}
ACCENT = (185, 240, 201)
INK = (238, 244, 238)
MUTED = (160, 178, 168)
GLASS = (14, 21, 18)


@lru_cache(None)
def font(weight: str, size: int, display: bool = False) -> ImageFont.FreeTypeFont:
    name = ("InterDisplay-" if display else "Inter-") + weight + ".otf"
    return ImageFont.truetype(FONT_DIR + name, size)


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t: float) -> float:
    t = min(1.0, max(0.0, t))
    c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def fade(t: float, t0: float, t1: float, fin: float = 0.25, fout: float = 0.25) -> float:
    if t < t0 or t > t1:
        return 0.0
    return min(ease((t - t0) / fin) if fin else 1, ease((t1 - t) / fout) if fout else 1)


def shadowed(layer: Image.Image, radius: int = 18, opacity: float = 0.55, offset=(0, 10)) -> Image.Image:
    """Add a soft drop shadow under an RGBA element (returns a larger image, same center)."""
    pad = radius * 3
    out = Image.new("RGBA", (layer.width + pad * 2, layer.height + pad * 2), (0, 0, 0, 0))
    a = layer.getchannel("A").point(lambda v: int(v * opacity))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 255))
    sh.putalpha(a)
    out.alpha_composite(sh, (pad + offset[0], pad + offset[1]))
    out = out.filter(ImageFilter.GaussianBlur(radius))
    out.alpha_composite(layer, (pad, pad))
    return out


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=f) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


@lru_cache(64)
def card_image(tier: str, source: str, title: str, line: str, buttons: bool, pressed: bool) -> Image.Image:
    """A notification card as Bricki delivers it. Pointer at bottom center."""
    w = 560
    pad = 28
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ft, fs, fl = font("SemiBold", 30), font("Medium", 21), font("SemiBold", 27)
    title_lines = wrap(probe, title, ft, w - pad * 2)
    line_lines = wrap(probe, f"“{line}”", fl, w - pad * 2 - 34)
    h = pad + 26 + 16 + len(title_lines) * 40 + 14 + len(line_lines) * 36 + pad + (74 if buttons else 0)
    img = Image.new("RGBA", (w, h + 18), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 22, fill=GLASS + (236,), outline=(255, 255, 255, 40), width=2)
    # pointer
    d.polygon([(w / 2 - 16, h - 2), (w / 2 + 16, h - 2), (w / 2, h + 16)], fill=GLASS + (236,))
    label, color = TIER[tier]
    y = pad
    d.ellipse((pad, y + 5, pad + 14, y + 19), fill=color)
    d.text((pad + 24, y - 2), label, font=font("Bold", 21), fill=color)
    d.text((w - pad, y - 2), source, font=fs, fill=MUTED, anchor="ra")
    y += 26 + 16
    for tl in title_lines:
        d.text((pad, y), tl, font=ft, fill=INK)
        y += 40
    y += 14
    # Bricki's line, with a tiny face marker
    d.rounded_rectangle((pad, y + 4, pad + 22, y + 26), 6, fill=(245, 189, 126))
    d.ellipse((pad + 6, y + 13, pad + 9, y + 16), fill=(33, 24, 17))
    d.ellipse((pad + 13, y + 13, pad + 16, y + 16), fill=(33, 24, 17))
    for ll in line_lines:
        d.text((pad + 34, y), ll, font=fl, fill=ACCENT)
        y += 36
    if buttons:
        y += 22
        bw = (w - pad * 2 - 14) // 2
        allow_fill = (255, 255, 255) if pressed else ACCENT
        d.rounded_rectangle((pad, y, pad + bw, y + 54), 14, fill=allow_fill)
        d.text((pad + bw / 2, y + 27), "Allow  ↵", font=font("SemiBold", 24), fill=(16, 34, 23), anchor="mm")
        d.rounded_rectangle((pad + bw + 14, y, w - pad, y + 54), 14, fill=(255, 255, 255, 22), outline=(255, 255, 255, 50), width=2)
        d.text((pad + bw + 14 + bw / 2, y + 27), "Later", font=font("SemiBold", 24), fill=INK, anchor="mm")
    return shadowed(img)


def paste_center(base: Image.Image, el: Image.Image, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0) -> None:
    if alpha <= 0.01:
        return
    if abs(scale - 1) > 0.01:
        el = el.resize((max(1, int(el.width * scale)), max(1, int(el.height * scale))), Image.BICUBIC)
    if alpha < 0.99:
        el = el.copy()
        el.putalpha(el.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(el, (int(cx - el.width / 2), int(cy - el.height / 2)))


@lru_cache(32)
def pill_image(tier: str, text: str) -> Image.Image:
    """Compact form of a card, shown while Bricki is on the move."""
    label, color = TIER[tier]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    fb, fr = font("Bold", 21), font("SemiBold", 23)
    w = int(probe.textlength(label, font=fb) + probe.textlength("  " + text, font=fr)) + 72
    img = Image.new("RGBA", (w, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, 51), 26, fill=GLASS + (236,), outline=(255, 255, 255, 40), width=2)
    d.polygon([(w / 2 - 11, 50), (w / 2 + 11, 50), (w / 2, 62)], fill=GLASS + (236,))
    d.ellipse((22, 19, 34, 31), fill=color)
    d.text((44, 26), label, font=fb, fill=color, anchor="lm")
    d.text((44 + probe.textlength(label, font=fb), 26), "  " + text, font=fr, fill=INK, anchor="lm")
    return shadowed(img, 14, 0.45, (0, 6))


SHADOW_PAD = 57


def draw_card(base: Image.Image, card: dict, t: float, anchor: tuple[float, float], expand: float) -> None:
    """Draw a tethered card. anchor = point just above Bricki's head (smoothed, maybe frozen);
    expand = 0 for the compact pill (moving), 1 for the full card (Bricki has stopped)."""
    t0, t1 = card["t0"], card["t1"]
    if not (t0 <= t <= t1):
        return
    pressed = card.get("press") is not None and t >= card["press"]
    line = card["after"] if pressed and card.get("after") else card["line"]
    buttons = card.get("buttons", False) and not (pressed and t > card["press"] + 0.35)
    a_in = ease_back((t - t0) / 0.35)
    a_out = ease((t1 - t) / 0.25)
    alpha = min(1.0, (t - t0) / 0.18, a_out)
    pop = 0.8 + 0.2 * min(1, a_in)
    rise = (1 - min(1, a_in)) * 24
    ax, ay = anchor
    layers = []
    if expand > 0.01:
        layers.append((card_image(card["tier"], card["source"], card["title"], line, buttons, pressed), expand))
    if expand < 0.99:
        short = card.get("short") or card["source"]
        layers.append((pill_image(card["tier"], short), 1 - expand))
    for img, weight in layers:
        body_h = img.height - 2 * SHADOW_PAD
        cx = float(np.clip(ax, img.width / 2 - SHADOW_PAD + 36, W - img.width / 2 + SHADOW_PAD - 36))
        cy = ay - body_h / 2
        # no room above: keep it on screen (the pointer still aims down at Bricki)
        cy = float(np.clip(cy, body_h / 2 + 28, H - body_h / 2 - 28))
        paste_center(base, img, cx, cy + rise, pop * (0.94 + 0.06 * weight), alpha * weight)


@lru_cache(32)
def chip_image(name: str, verb: str) -> Image.Image:
    fb, fr = font("Bold", 30), font("Medium", 30)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(probe.textlength(name, font=fb) + probe.textlength("  →  " + verb, font=fr)) + 84
    img = Image.new("RGBA", (w, 68), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, 67), 34, fill=GLASS + (215,), outline=(255, 255, 255, 36), width=2)
    d.ellipse((28, 27, 42, 41), fill=ACCENT)
    d.text((56, 34), name, font=fb, fill=INK, anchor="lm")
    x = 56 + probe.textlength(name, font=fb)
    d.text((x, 34), "  →  " + verb, font=fr, fill=ACCENT, anchor="lm")
    return shadowed(img, 14, 0.45, (0, 6))


def draw_chip(base: Image.Image, chip: dict, t: float) -> None:
    a = fade(t, chip["t0"], chip["t1"], 0.35, 0.3)
    if a <= 0:
        return
    img = chip_image(chip["name"], chip["verb"])
    x = 96 + img.width / 2 - 42 - (1 - a) * 40
    paste_center(base, img, x, H - 118, 1.0, a)


@lru_cache(32)
def title_image(text: str, size: int, weight: str, color: tuple, sub: str | None, sub_size: int) -> Image.Image:
    f = font(weight, size, display=True)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = text.split("\n")
    tw = max(probe.textlength(line, font=f) for line in lines)
    fs = font("Medium", sub_size, display=True)
    sw = probe.textlength(sub, font=fs) if sub else 0
    w = int(max(tw, sw)) + 40
    h = int(len(lines) * size * 1.15 + (sub_size * 1.9 if sub else 0)) + 40
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        d.text((w / 2, y), line, font=f, fill=color, anchor="ma")
        y += size * 1.15
    if sub:
        d.text((w / 2, y + sub_size * 0.5), sub, font=fs, fill=(205, 222, 212), anchor="ma")
    return shadowed(img, 22, 0.5, (0, 4))


def draw_title(base: Image.Image, title: dict, t: float) -> None:
    a = fade(t, title["t0"], title["t1"], title.get("fin", 0.4), title.get("fout", 0.35))
    if a <= 0:
        return
    img = title_image(title["text"], title.get("size", 76), title.get("weight", "SemiBold"), tuple(title.get("color", (255, 255, 255))), title.get("sub"), title.get("sub_size", 34))
    x, y = title.get("pos", (W / 2, H / 2))
    if y < H / 2 and title.get("scrim", True):
        base.alpha_composite(_scrim(), (0, 0)) if a > 0.99 else base.alpha_composite(_faded(_scrim(), a), (0, 0))
    rise = (1 - ease((t - title["t0"]) / 0.6)) * 26
    paste_center(base, img, x, y + rise, 1.0, a)


@lru_cache(1)
def _scrim() -> Image.Image:
    """Dark gradient at the top of frame so titles stay readable over a bright laptop screen."""
    h = 430
    g = np.linspace(0.62, 0, h) ** 1.6
    a = (np.repeat(g[:, None], W, 1) * 255).astype(np.uint8)
    img = Image.new("RGBA", (W, h), (6, 10, 8, 0))
    img.putalpha(Image.fromarray(a))
    return img


def _faded(img: Image.Image, a: float) -> Image.Image:
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


@lru_cache(4)
def key_image(pressed: bool) -> Image.Image:
    img = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    off = 6 if pressed else 0
    d.rounded_rectangle((20, 26, 280, 112), 20, fill=(40, 44, 42, 240))
    d.rounded_rectangle((20, 14 + off, 280, 100 + off), 20, fill=(236, 240, 236) if not pressed else ACCENT, outline=(255, 255, 255), width=2)
    d.text((150, 57 + off), "↵  Enter", font=font("SemiBold", 34), fill=(20, 30, 24), anchor="mm")
    return shadowed(img, 12, 0.4, (0, 6))


def draw_key(base: Image.Image, key: dict, t: float) -> None:
    a = fade(t, key["t0"], key["t1"], 0.2, 0.25)
    if a <= 0:
        return
    pressed = key["press"] <= t <= key["press"] + 0.22
    paste_center(base, key_image(pressed), W - 250, H - 150, 1.0, a)
    if t >= key["press"]:
        b = fade(t, key["press"], key["t1"], 0.1, 0.25)
        d = ImageDraw.Draw(base)
        d.text((W - 250, H - 62), "You approve.", font=font("Medium", 26), fill=(230, 240, 232, int(255 * b)), anchor="mm")


@lru_cache(32)
def notification_stack_image(i: int, source: str, title: str) -> Image.Image:
    """Generic OS-style notification used in the cold open."""
    w, h = 520, 116
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), 24, fill=(246, 246, 244, 245))
    hue = [(255, 120, 100), (90, 160, 255), (120, 200, 120), (255, 190, 80), (170, 130, 255)][i % 5]
    d.rounded_rectangle((20, 26, 84, 90), 16, fill=hue)
    d.text((104, 28), source.upper(), font=font("SemiBold", 19), fill=(120, 124, 122))
    d.text((w - 22, 28), "now", font=font("Medium", 19), fill=(140, 144, 142), anchor="ra")
    d.text((104, 56), title, font=font("SemiBold", 27), fill=(26, 28, 27))
    return shadowed(img, 16, 0.5, (0, 8))


def draw_polyline(d: ImageDraw.ImageDraw, pts: np.ndarray, color, width: int, progress: float = 1.0) -> None:
    if progress <= 0 or len(pts) < 2:
        return
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    total = seg.sum()
    keep, acc = [tuple(pts[0])], 0.0
    for p, s in zip(pts[1:], seg):
        if acc + s <= total * progress:
            keep.append(tuple(p))
            acc += s
        else:
            r = (total * progress - acc) / s if s else 0
            q = keep[-1]
            keep.append((q[0] + (p[0] - q[0]) * r, q[1] + (p[1] - q[1]) * r))
            break
    d.line(keep, fill=color, width=width, joint="curve")


def label_tag(d: ImageDraw.ImageDraw, x: float, y: float, name: str, verb: str, alpha: float) -> None:
    fb, fr = font("Bold", 24), font("Medium", 24)
    a = int(255 * alpha)
    w = d.textlength(name, font=fb) + d.textlength("  " + verb, font=fr) + 36
    x = min(max(x, w / 2 + 16), W - w / 2 - 16)
    d.rounded_rectangle((x - w / 2, y - 22, x + w / 2, y + 22), 22, fill=GLASS + (int(220 * alpha),))
    d.text((x - w / 2 + 18, y), name, font=fb, fill=INK + (a,), anchor="lm")
    d.text((x - w / 2 + 18 + d.textlength(name, font=fb), y), "  " + verb, font=fr, fill=ACCENT + (a,), anchor="lm")
