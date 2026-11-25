"""Генерация новогодней открытки (Pillow): текстурированная ёлка, объёмные игрушки, участники.

Рисуем в 2× разрешении и уменьшаем — так края и мелкие детали выглядят гладко.
"""
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import ORNAMENTS

SCALE = 2
W, H = 900, 1125          # итоговый размер открытки
SW, SH = W * SCALE, H * SCALE  # рабочее разрешение

# Цвета сцены
BG_TOP = (9, 14, 32)
BG_MID = (17, 30, 61)
BG_BOTTOM = (32, 62, 100)
PINE_LIGHT = (52, 168, 94)
PINE = (28, 122, 66)
PINE_DARK = (16, 84, 48)
PINE_DEEP = (9, 56, 33)
TRUNK = (92, 60, 33)
TRUNK_DARK = (58, 36, 19)
STAR_COLOR = (255, 206, 42)
SNOW = (240, 248, 255)

HAT_COLORS = [
    (220, 38, 38),    # красная
    (37, 99, 235),    # синяя
    (22, 163, 74),    # зелёная
    (168, 85, 247),   # фиолетовая
    (234, 88, 12),    # оранжевая
    (13, 148, 136),   # бирюзовая
]
SKIN_COLOR = (253, 224, 199)


# ────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ────────────────────────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color: str):
    hex_color = str(hex_color).lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1, c2, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _lighten(c, t: float):
    return _mix(c, (255, 255, 255), t)


def _darken(c, t: float):
    return _mix(c, (0, 0, 0), t)


def _shade(c, k: float):
    """Умножение яркости (k > 1 — светлее, k < 1 — темнее)."""
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _load_font(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


EMOJI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/emoji/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]


def _load_emoji_font(size: int):
    for path in EMOJI_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return None


# Символы, которые точно есть в обычных шрифтах (DejaVu/Liberation) — их можно рисовать текстом
SAFE_GLYPHS = "♥❤★☆❄☃✦✧✿☀☾✈✔✝☘♠♣♦♪♫☕⚑⌚✂✎✏✒✉✌✍☺☻♨⚡"

# Векторные медальоны для эмодзи, которых нет в шрифтах (или если эмодзи-шрифт не установлен)
VECTOR_ICONS = {
    "gift": {"🎁", "🛍", "🎀"},
    "diamond": {"💎", "💠", "🔷", "🔶"},
    "star": {"⭐", "🌟", "✨", "🌠", "💫"},
    "heart": {"❤", "💖", "💝", "💗", "💕", "♥"},
    "snow": {"❄", "🌨", "⛄", "☃", "🧊"},
    "tree": {"🎄", "🌲", "🌳"},
    "bell": {"🔔", "🛎", "🎐"},
    "santa": {"🎅", "🤶"},
    "flower": {"🌹", "🌷", "🌸", "💐"},
    "cake": {"🎂", "🍰", "🧁", "🍫"},
    "bear": {"🧸", "🐻", "🐼"},
    "rocket": {"🚀", "🛸"},
    "firework": {"🎆", "🎇", "🎉", "🎊"},
    "crown": {"👑", "🏆", "🥇", "🎖"},
    "moon": {"🌙", "🌛", "🌜", "☾"},
    "sun": {"☀", "🌞", "🌻"},
}


def _icon_kind(emoji: str, kind: str | None = None) -> str:
    for name, chars in VECTOR_ICONS.items():
        if emoji in chars:
            return name
    return "diamond" if kind in ("unique", "nft") else "gift"


def _draw_icon_shape(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, icon: str):
    """Векторный медальон: ромб/подарок/звезда и т.п. Цвета новогодние."""
    gold, gold_hi = (253, 224, 71), (255, 248, 200)
    line = max(1, int(SCALE * 1.4))
    if icon == "diamond":
        d = r * 0.92
        pts = [(cx, cy - d), (cx + d * 0.86, cy), (cx, cy + d), (cx - d * 0.86, cy)]
        draw.polygon(pts, fill=(125, 211, 252), outline=(224, 247, 255))
        draw.line([(cx - d * 0.86, cy), (cx + d * 0.86, cy)], fill=(224, 247, 255), width=line)
        draw.polygon([(cx, cy - d), (cx - d * 0.4, cy), (cx + d * 0.4, cy)], fill=(186, 230, 253))
    elif icon == "star":
        import math
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rad = r * 0.95 if i % 2 == 0 else r * 0.42
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        draw.polygon(pts, fill=gold, outline=gold_hi)
    elif icon == "heart":
        import math
        rr = r * 0.46
        cx1, cx2 = cx - rr * 0.92, cx + rr * 0.92
        draw.ellipse([cx1 - rr, cy - rr * 1.15, cx1 + rr, cy + rr * 0.85], fill=(251, 113, 133))
        draw.ellipse([cx2 - rr, cy - rr * 1.15, cx2 + rr, cy + rr * 0.85], fill=(251, 113, 133))
        pts = [(cx - math.sqrt(2) * rr * 0.98, cy + rr * 0.15),
               (cx + math.sqrt(2) * rr * 0.98, cy + rr * 0.15),
               (cx, cy + r * 1.02)]
        draw.polygon(pts, fill=(251, 113, 133))
    elif icon == "snow":
        for i in range(6):
            import math
            ang = i * math.pi / 3
            draw.line([(cx, cy), (cx + r * 0.92 * math.cos(ang), cy + r * 0.92 * math.sin(ang))],
                      fill=(224, 247, 255), width=line)
            # «веточки»
            for sign in (-1, 1):
                bx = cx + r * 0.62 * math.cos(ang)
                by = cy + r * 0.62 * math.sin(ang)
                ang2 = ang + sign * math.pi / 5
                draw.line([(bx, by), (bx + r * 0.3 * math.cos(ang2), by + r * 0.3 * math.sin(ang2))],
                          fill=(224, 247, 255), width=line)
    elif icon == "tree":
        draw.polygon([(cx, cy - r * 1.0), (cx - r * 0.72, cy + r * 0.45), (cx + r * 0.72, cy + r * 0.45)], fill=(74, 222, 128))
        draw.polygon([(cx, cy - r * 0.45), (cx - r * 0.92, cy + r * 0.85), (cx + r * 0.92, cy + r * 0.85)], fill=(34, 197, 94))
        draw.rectangle([cx - r * 0.16, cy + r * 0.75, cx + r * 0.16, cy + r * 1.05], fill=(120, 53, 15))
    elif icon == "bell":
        draw.pieslice([cx - r * 0.85, cy - r * 0.95, cx + r * 0.85, cy + r * 0.75], 180, 360, fill=gold)
        draw.rectangle([cx - r * 0.85, cy - r * 0.12, cx + r * 0.85, cy + r * 0.18], fill=gold)
        draw.ellipse([cx - r * 0.18, cy + r * 0.16, cx + r * 0.18, cy + r * 0.52], fill=gold_hi)
    elif icon == "firework":
        import math
        for i in range(8):
            ang = i * math.pi / 4
            draw.line([(cx + r * 0.25 * math.cos(ang), cy + r * 0.25 * math.sin(ang)),
                       (cx + r * 0.95 * math.cos(ang), cy + r * 0.95 * math.sin(ang))],
                      fill=gold_hi if i % 2 else (251, 191, 36), width=max(1, int(SCALE * 2)))
    else:  # gift — коробка с бантом
        bw, bh = r * 1.5, r * 1.25
        draw.rounded_rectangle([cx - bw / 2, cy - bh / 2 + r * 0.12, cx + bw / 2, cy + bh / 2], radius=r * 0.12, fill=(239, 68, 68))
        draw.rectangle([cx - r * 0.16, cy - bh / 2 + r * 0.12, cx + r * 0.16, cy + bh / 2], fill=gold)
        draw.rectangle([cx - bw / 2, cy - r * 0.05, cx + bw / 2, cy + r * 0.2], fill=gold)
        top = cy - bh / 2 + r * 0.12
        draw.ellipse([cx - r * 0.58, top - r * 0.02, cx - r * 0.04, top + r * 0.34], outline=gold, width=line)
        draw.ellipse([cx + r * 0.04, top - r * 0.02, cx + r * 0.58, top + r * 0.34], outline=gold, width=line)


def _draw_emoji(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    size: float,
    emoji: str,
    kind: str | None = None,
):
    """Эмодзи-медальон на подложке; без эмодзи-шрифта — векторный значок."""
    r = size * 0.62
    # Тёмный медальон-подложка с золотым ободком — общий для всех вариантов
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(37, 47, 74), outline=(253, 224, 71), width=max(1, int(SCALE * 1.4)))
    # мягкий верхний блик (полупрозрачный слой, чтобы не читался белым пятном)
    gloss = Image.new("RGBA", (int(r * 4) + 4, int(r * 4) + 4), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse(
        [r * 2 - r * 0.62 + 2, r * 2 - r * 0.82 + 2, r * 2 + r * 0.1 + 2, r * 2 - r * 0.04 + 2],
        fill=(255, 255, 255, 26),
    )
    gloss = gloss.filter(ImageFilter.GaussianBlur(max(1, int(SCALE * 2))))
    img.alpha_composite(gloss, (int(cx - r * 2 - 2), int(cy - r * 2 - 2)))

    font = _load_emoji_font(int(size))
    if font is not None:
        try:
            bbox = draw.textbbox((0, 0), emoji, font=font, embedded_color=True)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - w / 2, cy - h / 2 - bbox[1]), emoji, font=font, embedded_color=True)
            return
        except Exception:
            pass

    # Без эмодзи-шрифта: простые символы рисуем текстом, остальное — вектором
    if len(emoji) == 1 and emoji in SAFE_GLYPHS and ord(emoji) < 0x3000:
        f = _load_font(int(size * 0.78))
        bbox = draw.textbbox((0, 0), emoji, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw / 2, cy - th / 2 - bbox[1]), emoji, font=f, fill=(255, 241, 176))
        return
    _draw_icon_shape(draw, cx, cy, r * 0.66, _icon_kind(emoji, kind))


def _s(v: float) -> float:
    """Пересчёт координат из итогового масштаба в рабочее разрешение."""
    return v * SCALE


# ────────────────────────────────────────────────────────────────────────────
#  Фон и сцена
# ────────────────────────────────────────────────────────────────────────────
def _draw_background(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Звёздное небо с градиентом, сиянием и мягкими сугробами."""
    # Гладкий градиент по трём опорным цветам
    for y in range(SH):
        t = y / SH
        if t < 0.55:
            c = _mix(BG_TOP, BG_MID, t / 0.55)
        else:
            c = _mix(BG_MID, BG_BOTTOM, (t - 0.55) / 0.45)
        draw.line([(0, y), (SW, y)], fill=c)

    # Дальние звёзды (мелкая крошка)
    rnd = random.Random(7)
    for _ in range(260):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH * 0.8)
        r = rnd.uniform(0.6, 1.7) * SCALE
        a = rnd.randint(40, 150)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))

    # Крупные звёзды с крестиком-бликом
    for _ in range(22):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH * 0.62)
        r = rnd.uniform(1.6, 3.2) * SCALE
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 220))
        arm = r * 2.6
        draw.line([(x - arm, y), (x + arm, y)], fill=(255, 255, 255, 70), width=max(1, int(SCALE)))
        draw.line([(x, y - arm), (x, y + arm)], fill=(255, 255, 255, 70), width=max(1, int(SCALE)))

    # Северное сияние — размытое цветное пятно
    aurora = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aurora)
    ad.ellipse([-_s(120), _s(30), SW * 0.72, _s(300)], fill=(16, 185, 129, 52))
    ad.ellipse([SW * 0.35, _s(-40), SW + _s(120), _s(240)], fill=(56, 189, 248, 46))
    ad.ellipse([SW * 0.2, _s(90), SW * 0.95, _s(330)], fill=(168, 85, 247, 34))
    aurora = aurora.filter(ImageFilter.GaussianBlur(_s(46)))
    img.alpha_composite(aurora)

    # Луна с мягким гало
    moon = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    mx, my, mr = _s(680), _s(96), _s(34)
    md.ellipse([mx - mr * 2.1, my - mr * 2.1, mx + mr * 2.1, my + mr * 2.1], fill=(253, 230, 138, 26))
    moon = moon.filter(ImageFilter.GaussianBlur(_s(18)))
    img.alpha_composite(moon)
    draw.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(254, 240, 138))
    draw.ellipse([mx - mr * 0.72, my - mr * 0.9, mx + mr * 0.3, my + mr * 0.1], fill=(255, 251, 214))
    # «Тени» кратеров
    for dx, dy, rr in ((-0.34, 0.2, 0.18), (0.22, -0.26, 0.13), (0.3, 0.32, 0.1)):
        cx, cy, cr = mx + mr * dx, my + mr * dy, mr * rr
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(233, 213, 112))


def _draw_ground(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Сугробы с плавными краями, искрами и тенью под ёлкой."""
    # Мягкое холодное свечение у горизонта
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-_s(160), _s(700), SW + _s(160), SH + _s(140)], fill=(148, 197, 255, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(_s(40)))
    img.alpha_composite(glow)

    # Задний сугроб (светлее, дальше)
    draw.ellipse([-_s(120), _s(858), SW * 0.66, SH + _s(70)], fill=(214, 228, 245))
    draw.ellipse([SW * 0.42, _s(868), SW + _s(140), SH + _s(90)], fill=(233, 241, 252))

    # Передний сугроб с объёмным низом
    draw.ellipse([-_s(180), _s(902), SW * 0.52, SH + _s(120)], fill=(255, 255, 255))
    draw.ellipse([SW * 0.33, _s(908), SW + _s(200), SH + _s(130)], fill=(248, 252, 255))
    draw.ellipse([SW * 0.24, _s(930), SW * 0.86, SH + _s(150)], fill=(226, 238, 250))

    # Тень под ёлкой
    shadow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse([_s(112), _s(872), _s(688), _s(948)], fill=(12, 26, 52, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(_s(16)))
    img.alpha_composite(shadow)

    # Блёстки на снегу
    rnd = random.Random(21)
    for _ in range(150):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(_s(884), SH)
        if not (SW * 0.30 < x < SW * 0.70 and y < _s(950)):
            r = rnd.uniform(0.8, 2.4) * SCALE
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(120, 230)))


def _draw_snowfall(draw: ImageDraw.ImageDraw):
    """Крупные снежинки перед ёлкой — добавляют глубину."""
    rnd = random.Random(33)
    for _ in range(70):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH)
        r = rnd.uniform(1.4, 3.6) * SCALE
        a = rnd.randint(90, 210)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))


# ────────────────────────────────────────────────────────────────────────────
#  Ёлка
# ────────────────────────────────────────────────────────────────────────────
def _pine_tier(cx: float, top: float, bottom: float, half_bottom: float, teeth: int = 9):
    """Силуэт яруса ёлки: пила из «лап» по бокам и провисший зубчатый низ."""
    height = bottom - top
    left: list[tuple[float, float]] = [(cx, top)]
    for k in range(teeth):
        t_in = k / teeth
        t_out = (k + 0.62) / teeth
        w_in = half_bottom * (t_in ** 0.92) * 0.74
        w_out = half_bottom * (t_out ** 0.92)
        left.append((cx - w_in, top + height * t_in))
        left.append((cx - w_out, top + height * t_out + height * 0.018))

    # Зубчатый низ: несколько провисших «лап» от левого края к правому
    bottom_pts: list[tuple[float, float]] = []
    fringe = 5
    for i in range(fringe * 2 + 1):
        t = i / (fringe * 2)
        x = cx - half_bottom + 2 * half_bottom * t
        sag = (height * 0.055 if i % 2 == 0 else -height * 0.006)
        bottom_pts.append((x, bottom + sag))

    right = [(2 * cx - x, y) for (x, y) in reversed(left[1:])]
    return left + bottom_pts + right


def _draw_tier(img: Image.Image, draw: ImageDraw.ImageDraw, poly, y0: float, y1: float,
               base_color, seed: int):
    """Ярус: мягкая тень, градиентная заливка, боковой объём, хвоя и снег на лапах."""
    # 1) Мягкая тень под ярусом
    shadow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        [(x + _s(5), y + _s(8)) for x, y in poly], fill=(6, 20, 12, 110)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(_s(10)))
    img.alpha_composite(shadow)

    # 2) Маска яруса
    mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)

    # 3) Градиент по вертикали + боковой свет
    grad = Image.new("RGB", (SW, SH), base_color)
    gd = ImageDraw.Draw(grad)
    for y in range(int(y0), int(y1) + 1):
        t = (y - y0) / max(1.0, (y1 - y0))
        c = _mix(_lighten(base_color, 0.26), _darken(base_color, 0.42), t ** 0.9)
        gd.line([(0, y), (SW, y)], fill=c)
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [_s(120), y0 + (y1 - y0) * 0.12, _s(400), y1], fill=(255, 255, 255, 40)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(_s(40)))
    img.paste(grad, (0, 0), mask)
    img.alpha_composite(Image.composite(glow, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))

    # 4) Хвоя: мелкие штрихи внутри маски
    rnd = random.Random(seed)
    needles = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    nd = ImageDraw.Draw(needles)
    mpx = mask.load()
    mw, mh = mask.size
    drawn, tries = 0, 0
    while drawn < 3200 and tries < 60000:
        tries += 1
        x = rnd.randint(0, mw - 1)
        y = rnd.randint(max(0, int(y0)), min(mh - 1, int(y1)))
        if mpx[x, y] < 200:
            continue
        drawn += 1
        ang = rnd.uniform(-0.9, 0.9)
        ln = rnd.uniform(2.0, 5.0) * SCALE * 0.55
        col = (255, 255, 255, rnd.randint(10, 28)) if rnd.random() < 0.4 else (5, 40, 24, rnd.randint(14, 34))
        nd.line(
            [(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln + ln * 0.7)],
            fill=col, width=max(1, int(SCALE * 0.85)),
        )
    img.alpha_composite(Image.composite(needles, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))

    # 5) Снег на «лапах» — только в нижней трети яруса, маленькими мазками
    snow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(snow)
    xs = [p[0] for p in poly]
    cx_est = (min(xs) + max(xs)) / 2
    for x, y in poly:
        if y < y1 - (y1 - y0) * 0.30:
            continue
        if abs(x - cx_est) > (max(xs) - min(xs)) * 0.46:
            continue
        rr = rnd.uniform(2.6, 5.0) * SCALE * 0.6
        sd.ellipse([x - rr, y - rr * 0.6, x + rr, y + rr * 0.6], fill=(255, 255, 255, 150))
    snow = snow.filter(ImageFilter.GaussianBlur(_s(1.2)))
    img.alpha_composite(Image.composite(snow, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))


def _draw_trunk(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Ствол с текстурой коры и снегом у основания."""
    x0, x1 = _s(368), _s(432)
    y0, y1 = _s(820), _s(918)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=_s(8), fill=TRUNK)
    # Кора: вертикальные полосы разной темноты
    rnd = random.Random(5)
    for _ in range(46):
        xx = rnd.uniform(x0 + _s(4), x1 - _s(4))
        yy = rnd.uniform(y0 + _s(4), y1 - _s(10))
        ln = rnd.uniform(_s(8), _s(30))
        col = _darken(TRUNK, rnd.uniform(0.25, 0.55)) if rnd.random() < 0.6 else _lighten(TRUNK, 0.22)
        draw.line([(xx, yy), (xx + rnd.uniform(-_s(2), _s(2)), yy + ln)], fill=col, width=max(1, int(rnd.uniform(1, 2.4) * SCALE)))
    # Объём ствола: блик слева, тень справа
    draw.rectangle([x0 + _s(6), y0, x0 + _s(20), y1], fill=_lighten(TRUNK, 0.18))
    draw.rectangle([x1 - _s(18), y0, x1 - _s(4), y1], fill=_darken(TRUNK, 0.32))
    # Снег у основания
    draw.ellipse([x0 - _s(16), y1 - _s(16), x1 + _s(16), y1 + _s(12)], fill=(250, 252, 255))
    draw.ellipse([x0 - _s(4), y1 - _s(22), x1 + _s(2), y1 - _s(4)], fill=(255, 255, 255))


def _draw_tree(img: Image.Image, draw: ImageDraw.ImageDraw):
    cx = _s(400)
    _draw_trunk(img, draw)

    tiers = [
        # (top, bottom, half_bottom, color, seed, teeth)
        (_s(70), _s(420), _s(152), PINE_LIGHT, 11, 7),
        (_s(258), _s(628), _s(214), PINE, 23, 8),
        (_s(444), _s(858), _s(288), PINE_DARK, 37, 9),
    ]
    for top, bottom, hbot, color, seed, teeth in tiers:
        poly = _pine_tier(cx, top, bottom, hbot, teeth=teeth)
        _draw_tier(img, draw, poly, top, bottom, color, seed)

    # Гирлянда-провода (тёмная нить + лампочки)
    wires = [
        ((_s(300), _s(318)), (_s(400), _s(376)), (_s(500), _s(308))),
        ((_s(250), _s(532)), (_s(400), _s(606)), (_s(548), _s(520))),
        ((_s(196), _s(700)), (_s(400), _s(790)), (_s(602), _s(688))),
    ]
    for (p0, p1, p2) in wires:
        pts = []
        for i in range(41):
            t = i / 40
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            pts.append((x, y))
        draw.line(pts, fill=(18, 40, 30), width=max(1, int(1.6 * SCALE)))

    # Светящиеся лампочки
    bulbs = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bulbs)
    palette = [(255, 214, 102), (244, 63, 94), (56, 189, 248), (52, 211, 153), (192, 132, 252)]
    idx = 0
    for (p0, p1, p2), count in zip(wires, (8, 10, 12)):
        for i in range(count):
            t = (i + 0.5) / count
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            col = palette[idx % len(palette)]
            r = _s(4.6)
            bd.ellipse([x - r * 2.0, y - r * 2.0, x + r * 2.0, y + r * 2.0], fill=col + (38,))
            bd.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))
            bd.ellipse([x - r * 0.34, y - r * 0.42, x + r * 0.34, y + r * 0.18], fill=(255, 255, 255, 230))
            idx += 1
    glow = bulbs.filter(ImageFilter.GaussianBlur(_s(6)))
    img.alpha_composite(glow)
    img.alpha_composite(bulbs)

    # Макушка
    _draw_star(img, draw, cx, _s(84), _s(46), STAR_COLOR)


def _draw_star(img: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color):
    # Сияние вокруг звезды
    halo = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([cx - r * 2.4, cy - r * 2.4, cx + r * 2.4, cy + r * 2.4], fill=(255, 214, 60, 90))
    halo = halo.filter(ImageFilter.GaussianBlur(_s(16)))
    img.alpha_composite(halo)

    def pts(radius):
        out = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            rad = radius if i % 2 == 0 else radius * 0.44
            out.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
        return out

    outer = pts(r)
    draw.polygon([(x + _s(3), y + _s(4)) for x, y in outer], fill=(171, 118, 8))
    draw.polygon(outer, fill=color, outline=(214, 158, 12))
    # Половинка звезды светлее — объём
    draw.polygon([(cx, cy)] + [p for p in outer if p[0] <= cx] + [(cx, cy - r)], fill=_lighten(color, 0.35))
    draw.polygon(pts(r * 0.55), fill=(255, 246, 196))


# ────────────────────────────────────────────────────────────────────────────
#  Игрушки (объёмные)
# ────────────────────────────────────────────────────────────────────────────
def _hang(draw: ImageDraw.ImageDraw, x: float, y: float, top_y: float):
    """Петелька и ниточка от точки крепления."""
    draw.line([(x, top_y), (x, y - _s(13))], fill=(226, 232, 240, 190), width=max(1, int(1.3 * SCALE)))
    draw.ellipse([x - _s(3), y - _s(16), x + _s(3), y - _s(10)], outline=(250, 204, 21), width=max(1, int(1.4 * SCALE)))


def _radial_ball(img: Image.Image, cx: float, cy: float, r: float, rgb):
    """Шар с радиальным градиентом, бликом и тенью."""
    x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
    steps = 26
    for i in range(steps, 0, -1):
        t = i / steps
        rr = r * t
        col = _mix(_shade(rgb, 1.22), _darken(rgb, 0.62), t ** 0.8)
        d = ImageDraw.Draw(img)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)
    d = ImageDraw.Draw(img)
    # Кольцо вокруг шара для чёткости
    d.ellipse([x0, y0, x1, y1], outline=_darken(rgb, 0.5), width=max(1, int(1.2 * SCALE)))
    # Блик
    d.ellipse([cx - r * 0.55, cy - r * 0.62, cx - r * 0.05, cy - r * 0.2], fill=(255, 255, 255, 150))
    d.ellipse([cx - r * 0.42, cy - r * 0.52, cx - r * 0.22, cy - r * 0.36], fill=(255, 255, 255, 225))
    # Нижний отражённый свет
    d.arc([cx - r * 0.7, cy + r * 0.1, cx + r * 0.7, cy + r * 0.95], 20, 160, fill=_lighten(rgb, 0.45), width=max(1, int(1.6 * SCALE)))


def _draw_ball(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(26))
    _radial_ball(img, x, y, _s(19), rgb)


def _draw_snowflake(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(21))
    d = draw
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([x - _s(22), y - _s(22), x + _s(22), y + _s(22)], fill=rgb + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(_s(8)))
    img.alpha_composite(glow)
    r = _s(17)
    for angle in range(0, 360, 60):
        rad = math.radians(angle)
        d.line([(x, y), (x + r * math.cos(rad), y + r * math.sin(rad))],
               fill=rgb, width=max(2, int(2.6 * SCALE)))
        for t in (0.48, 0.76):
            bx, by = x + r * t * math.cos(rad), y + r * t * math.sin(rad)
            for da in (-38, 38):
                r2 = rad + math.radians(da)
                d.line([(bx, by), (bx + r * 0.34 * math.cos(r2), by + r * 0.34 * math.sin(r2))],
                       fill=rgb, width=max(1, int(1.8 * SCALE)))
    d.ellipse([x - _s(3.4), y - _s(3.4), x + _s(3.4), y + _s(3.4)], fill=(255, 255, 255))


def _draw_gift(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(24))
    s = _s(16)
    # Коробка с объёмом
    draw.rectangle([x - s, y - s + _s(6), x + s, y + s], fill=rgb)
    draw.rectangle([x + s * 0.35, y - s + _s(6), x + s, y + s], fill=_darken(rgb, 0.28))
    draw.rectangle([x - s, y - s + _s(6), x - s * 0.4, y + s], fill=_lighten(rgb, 0.22))
    # Крышка
    draw.rectangle([x - s - _s(2), y - s - _s(3), x + s + _s(2), y - s + _s(7)], fill=_lighten(rgb, 0.12))
    draw.rectangle([x - s - _s(2), y - s + _s(1), x + s + _s(2), y - s + _s(7)], fill=_darken(rgb, 0.18))
    # Ленты
    gold = (253, 224, 71)
    draw.rectangle([x - _s(3), y - s - _s(3), x + _s(3), y + s], fill=gold)
    draw.rectangle([x - s - _s(2), y - _s(1), x + s + _s(2), y + _s(3)], fill=gold)
    # Бант
    for sx in (-1, 1):
        draw.ellipse([x + sx * _s(11) - _s(9), y - s - _s(12), x + sx * _s(11) + _s(9), y - s + _s(2)],
                     fill=gold, outline=_darken(gold, 0.35))
    draw.ellipse([x - _s(4), y - s - _s(8), x + _s(4), y - s], fill=_lighten(gold, 0.3))


def _draw_bell(img, draw, x, y, color_hex):
    gold = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(22))
    # Основа колокольчика
    top = y - _s(14)
    bot = y + _s(9)
    for i in range(16, 0, -1):
        t = i / 16
        rr = _s(15) * t
        col = _mix(_lighten(gold, 0.45), _darken(gold, 0.42), 1 - t)
        draw.ellipse([x - rr, top - rr * 0.55, x + rr, bot + rr * 0.28], fill=col)
    draw.polygon([(x - _s(15), y + _s(4)), (x + _s(15), y + _s(4)), (x + _s(17), y + _s(11)), (x - _s(17), y + _s(11))],
                 fill=_darken(gold, 0.24))
    # Ободок и язычок
    draw.rounded_rectangle([x - _s(18), y + _s(8), x + _s(18), y + _s(14)], radius=_s(3), fill=_lighten(gold, 0.2))
    draw.ellipse([x - _s(5), y + _s(13), x + _s(5), y + _s(22)], fill=(150, 104, 10))
    draw.ellipse([x - _s(3.2), y + _s(14.5), x + _s(2), y + _s(18)], fill=(226, 178, 52))
    # Блик и ручка
    draw.ellipse([x - _s(9), y - _s(11), x - _s(2), y + _s(2)], fill=(255, 250, 220, 150))
    draw.arc([x - _s(7), y - _s(24), x + _s(7), y - _s(13)], 200, 340, fill=_darken(gold, 0.3), width=max(1, int(2 * SCALE)))


def _draw_candy(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(20))
    # Обёртки
    for sx in (-1, 1):
        draw.polygon(
            [(x + sx * _s(9), y), (x + sx * _s(22), y - _s(9)), (x + sx * _s(19), y), (x + sx * _s(22), y + _s(9))],
            fill=_lighten(rgb, 0.1), outline=_darken(rgb, 0.3),
        )
    # Корпус конфеты со спиралью
    r = _s(11)
    draw.ellipse([x - r, y - r, x + r, y + r], fill=_lighten(rgb, 0.22))
    for i in range(3):
        off = i * _s(2.4)
        draw.arc([x - r + off, y - r, x + r + off, y + r], 200, 340, fill=_darken(rgb, 0.12), width=max(1, int(1.8 * SCALE)))
    draw.arc([x - r, y - r, x + r, y + r], 120, 300, fill=(255, 255, 255), width=max(1, int(2 * SCALE)))
    draw.ellipse([x - _s(5), y - _s(6), x - _s(1), y - _s(2)], fill=(255, 255, 255, 210))


def _draw_angel(img, draw, x, y, color_hex):
    """Рождественский ангелочек: пушистые крылья, платье с градиентом, чистый нимб."""
    rgb = _hex_to_rgb(color_hex) if color_hex else (253, 224, 71)
    robe_light = _lighten(rgb, 0.55)
    robe_dark = _darken(rgb, 0.30)

    # ── 1. Свечение вокруг фигурки
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [x - _s(40), y - _s(38), x + _s(40), y + _s(30)], fill=(255, 247, 214, 72)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(_s(12)))
    img.alpha_composite(glow)

    # ── 2. Крылья: три слоя перьев, сзади фигурки
    for sx in (-1, 1):
        layers = [
            (24, 20, (238, 243, 252), (203, 213, 226)),   # дальний слой
            (19, 15, (250, 252, 255), (214, 223, 236)),   # средний
            (14, 11, (255, 255, 255), (226, 232, 240)),   # ближний
        ]
        for reach, height, fill, edge in layers:
            d = draw
            d.polygon(
                [
                    (x + sx * _s(3), y - _s(6)),
                    (x + sx * _s(reach * 0.55), y - _s(height)),
                    (x + sx * _s(reach), y - _s(height * 0.55)),
                    (x + sx * _s(reach * 0.92), y + _s(height * 0.18)),
                    (x + sx * _s(reach * 0.45), y + _s(height * 0.5)),
                    (x + sx * _s(6), y + _s(6)),
                ],
                fill=fill,
                outline=edge,
            )
            # Прожилки перьев
            for k in range(3):
                f = 0.35 + k * 0.22
                d.line(
                    [
                        (x + sx * _s(5 + reach * f * 0.85), y - _s(height * (1 - f) * 0.35)),
                        (x + sx * _s(reach * (0.5 + f * 0.45)), y + _s(height * (0.15 + f * 0.2))),
                    ],
                    fill=(210, 220, 234), width=max(1, int(SCALE * 0.9)),
                )

    # ── 3. Платье-конус с градиентом и мягкими складками
    top_y = y - _s(8)
    bot_y = y + _s(22)
    half_top, half_bot = _s(4.5), _s(15)
    for i in range(26):
        t = i / 25
        yy = top_y + (bot_y - top_y) * t
        hw = half_top + (half_bot - half_top) * (t ** 1.15)
        col = _mix(robe_light, robe_dark, t ** 0.9)
        draw.line([(x - hw, yy), (x + hw, yy)], fill=col, width=max(2, int(SCALE * 2.2)))
        # Складки
        if i % 4 == 0:
            draw.line([(x - hw * 0.55, yy), (x - hw * 0.2, yy + _s(2))], fill=_darken(rgb, 0.42))
            draw.line([(x + hw * 0.55, yy), (x + hw * 0.2, yy + _s(2))], fill=_darken(rgb, 0.42))

    # Силуэт платья и золотой поясок
    draw.line([(x - half_top, top_y), (x - half_bot, bot_y)], fill=robe_dark, width=max(1, int(SCALE)))
    draw.line([(x + half_top, top_y), (x + half_bot, bot_y)], fill=robe_dark, width=max(1, int(SCALE)))
    draw.ellipse([x - half_bot, bot_y - _s(3), x + half_bot, bot_y + _s(3)], fill=_lighten(rgb, 0.28))
    draw.line([(x - _s(6), y + _s(3)), (x + _s(6), y + _s(3))], fill=(253, 224, 71), width=max(1, int(SCALE * 1.8)))

    # ── 4. Ручки
    for sx in (-1, 1):
        draw.line([(x + sx * _s(4), y - _s(2)), (x + sx * _s(13), y + _s(7))],
                  fill=SKIN_COLOR, width=max(2, int(SCALE * 2.3)))
        draw.ellipse([x + sx * _s(13) - _s(2.8), y + _s(4.2), x + sx * _s(13) + _s(2.8), y + _s(9.8)], fill=SKIN_COLOR)

    # ── 5. Голова, волосы, лицо
    hx, hy, hr = x, y - _s(18), _s(8.5)
    for i in range(12, 0, -1):
        t = i / 12
        rr = hr * t
        draw.ellipse([hx - rr, hy - rr, hx + rr, hy + rr],
                     fill=_mix((255, 249, 238), (232, 194, 162), 1 - t))
    # Волосы: шапочка сверху + локоны у щёк
    draw.chord([hx - hr * 1.04, hy - hr * 1.12, hx + hr * 1.04, hy + hr * 0.55], 180, 360, fill=(198, 150, 92))
    draw.ellipse([hx - hr * 1.02, hy - hr * 0.32, hx - hr * 0.55, hy + hr * 0.62], fill=(186, 138, 82))
    draw.ellipse([hx + hr * 0.55, hy - hr * 0.32, hx + hr * 1.02, hy + hr * 0.62], fill=(186, 138, 82))
    # Глазки
    for sx in (-1, 1):
        draw.ellipse([hx + sx * _s(3.1) - _s(1.25), hy - _s(1.4), hx + sx * _s(3.1) + _s(1.25), hy + _s(1.1)], fill=(38, 46, 62))
        draw.ellipse([hx + sx * _s(3.1) - _s(0.5), hy - _s(0.9), hx + sx * _s(3.1) + _s(0.3), hy + _s(0.1)], fill=(255, 255, 255))
    # Улыбка и румянец
    draw.arc([hx - _s(3), hy + _s(1.2), hx + _s(3), hy + _s(4.8)], 20, 160, fill=(192, 84, 80), width=max(1, int(SCALE * 1.3)))
    draw.ellipse([hx - _s(5.6), hy + _s(1.2), hx - _s(2.8), hy + _s(3.4)], fill=(250, 188, 188, 120))
    draw.ellipse([hx + _s(2.8), hy + _s(1.2), hx + _s(5.6), hy + _s(3.4)], fill=(250, 188, 188, 120))

    # ── 6. Нимб: кольцо + мягкое свечение (без «полос»)
    halo_top = hy - _s(24)
    halo_bot = hy - _s(12)
    halo = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([hx - _s(11.5), halo_top, hx + _s(11.5), halo_bot], outline=(255, 222, 84, 235), width=max(2, int(SCALE * 2.0)))
    halo = halo.filter(ImageFilter.GaussianBlur(_s(3.5)))
    img.alpha_composite(halo)
    draw.ellipse([hx - _s(10.5), halo_top + _s(1.2), hx + _s(10.5), halo_bot - _s(1.2)],
                 outline=(255, 236, 140), width=max(1, int(SCALE * 1.5)))
    draw.arc([hx - _s(10.5), halo_top + _s(1.2), hx + _s(10.5), halo_bot - _s(1.2)], 190, 350,
             fill=(255, 253, 220), width=max(1, int(SCALE * 1.2)))

    # ── 7. Звёздочка на платье
    sx0, sy0 = x, y + _s(10)
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = _s(3.4) if i % 2 == 0 else _s(1.5)
        pts.append((sx0 + rr * math.cos(a), sy0 + rr * math.sin(a)))
    draw.polygon(pts, fill=(255, 246, 190), outline=(214, 158, 12))


def _draw_crystal(img, draw, x, y, color_hex):
    """Кристалл: огранка с бликами и внутренним свечением."""
    rgb = _hex_to_rgb(color_hex)
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([x - _s(26), y - _s(26), x + _s(26), y + _s(26)], fill=rgb + (80,))
    glow = glow.filter(ImageFilter.GaussianBlur(_s(10)))
    img.alpha_composite(glow)

    top = (x, y - _s(22))
    mid_l = (x - _s(12), y - _s(4))
    mid_r = (x + _s(12), y - _s(4))
    bottom = (x, y + _s(20))
    left = (x - _s(8), y + _s(10))
    right = (x + _s(8), y + _s(10))
    # Грани с разной яркостью — объём
    draw.polygon([top, mid_l, bottom], fill=_lighten(rgb, 0.42))
    draw.polygon([top, mid_r, bottom], fill=_darken(rgb, 0.28))
    draw.polygon([mid_l, left, bottom], fill=_lighten(rgb, 0.18))
    draw.polygon([mid_r, right, bottom], fill=_darken(rgb, 0.5))
    draw.polygon([top, mid_r, mid_l], fill=_lighten(rgb, 0.62))
    draw.polygon([mid_l, mid_r, bottom], fill=rgb)
    # Контур и блики
    draw.line([top, mid_r, right, bottom, left, mid_l, top], fill=(255, 255, 255), width=max(1, int(1.4 * SCALE)))
    draw.line([top, bottom], fill=(255, 255, 255, 210), width=max(1, int(1.2 * SCALE)))
    draw.line([mid_l, mid_r], fill=(255, 255, 255, 170), width=max(1, int(1.2 * SCALE)))
    draw.polygon([(x - _s(6), y - _s(12)), (x - _s(2), y - _s(6)), (x - _s(6), y + _s(6))], fill=(255, 255, 255, 200))
    draw.ellipse([x + _s(2), y - _s(9), x + _s(5), y - _s(6)], fill=(255, 255, 255, 230))
    # Искры
    for dx, dy, rr in ((_s(15), -_s(14), _s(2.4)), (-_s(14), _s(6), _s(1.8)), (_s(10), _s(16), _s(1.6))):
        draw.ellipse([x + dx - rr, y + dy - rr, x + dx + rr, y + dy + rr], fill=(255, 255, 255, 220))


DRAWERS = {
    "ball": _draw_ball,
    "star": lambda img, d, x, y, c: _draw_star(img, d, x, y, _s(20), _hex_to_rgb(c)),
    "snowflake": _draw_snowflake,
    "gift": _draw_gift,
    "bell": _draw_bell,
    "candy": _draw_candy,
    "angel": _draw_angel,
    "crystal": _draw_crystal,
}


# ────────────────────────────────────────────────────────────────────────────
#  Участники под ёлкой
# ────────────────────────────────────────────────────────────────────────────
def _draw_person(img: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, hat_rgb, scale: float = 1.0):
    """Маленький человечек в новогодней шапочке и шубке (cy — низ ног)."""
    s = scale
    body_w, body_h = _s(13) * s, _s(21) * s
    head_r = _s(8.5) * s

    # Тень
    shadow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([cx - _s(13) * s, cy - _s(4) * s, cx + _s(13) * s, cy + _s(2) * s], fill=(10, 22, 44, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(_s(3)))
    img.alpha_composite(shadow)

    d = draw
    dark_hat = _darken(hat_rgb, 0.35)
    light_hat = _lighten(hat_rgb, 0.25)
    # Шубка с градиентом
    top, bottom = cy - body_h, cy - _s(2) * s
    half = body_w / 2
    for i in range(12):
        t = i / 11
        yy = top + (bottom - top) * t
        hw = half * (0.86 + 0.14 * t)
        col = _mix(dark_hat, light_hat, 0.25 + 0.5 * (1 - t))
        d.line([(cx - hw, yy), (cx + hw, yy)], fill=col, width=max(2, int(2.2 * SCALE)))
    d.rounded_rectangle([cx - half, top, cx + half, bottom], radius=_s(4) * s, outline=_darken(hat_rgb, 0.55))
    # Меховая опушка и воротник
    d.rounded_rectangle([cx - half - _s(1) * s, bottom - _s(5) * s, cx + half + _s(1) * s, bottom], radius=_s(2.4) * s, fill=(255, 255, 255))
    d.rounded_rectangle([cx - half * 0.9, top, cx + half * 0.9, top + _s(3.4) * s], radius=_s(1.8) * s, fill=(248, 250, 252))
    # Рукавички
    for sx in (-1, 1):
        d.ellipse([cx + sx * (half + _s(2.6) * s) - _s(3) * s, cy - _s(12) * s,
                   cx + sx * (half + _s(2.6) * s) + _s(3) * s, cy - _s(6) * s], fill=dark_hat)

    # Голова
    head_y = cy - body_h - head_r * 0.72
    for i in range(8, 0, -1):
        t = i / 8
        rr = head_r * t
        d.ellipse([cx - rr, head_y - rr, cx + rr, head_y + rr], fill=_mix((255, 240, 224), SKIN_COLOR, 1 - t))
    # Глазки, улыбка, румянец
    for sx in (-1, 1):
        d.ellipse([cx + sx * _s(3.4) * s - _s(1.1) * s, head_y - _s(1.2) * s,
                   cx + sx * _s(3.4) * s + _s(1.1) * s, head_y + _s(0.8) * s], fill=(32, 42, 60))
    d.arc([cx - _s(3.2) * s, head_y + _s(1.0) * s, cx + _s(3.2) * s, head_y + _s(4.8) * s], 15, 165,
          fill=(150, 76, 40), width=max(1, int(1.5 * SCALE)))
    d.ellipse([cx - _s(6.4) * s, head_y + _s(1.4) * s, cx - _s(3.4) * s, head_y + _s(3.4) * s], fill=(250, 186, 186, 130))
    d.ellipse([cx + _s(3.4) * s, head_y + _s(1.4) * s, cx + _s(6.4) * s, head_y + _s(3.4) * s], fill=(250, 186, 186, 130))

    # Шапочка: конус с загнутым кончиком и помпоном
    hat_base_y = head_y - head_r * 0.5
    tip_x = cx + head_r * 0.62
    tip_y = head_y - head_r * 2.35
    d.polygon(
        [(cx - head_r * 1.06, hat_base_y), (cx + head_r * 1.06, hat_base_y), (tip_x, tip_y)],
        fill=hat_rgb, outline=_darken(hat_rgb, 0.4),
    )
    d.polygon([(cx - head_r * 1.06, hat_base_y), (cx, hat_base_y - head_r * 0.9), (tip_x, tip_y), (cx - head_r * 0.2, hat_base_y)],
              fill=light_hat)
    d.rounded_rectangle([cx - head_r * 1.14, hat_base_y - head_r * 0.34, cx + head_r * 1.14, hat_base_y + head_r * 0.2],
                        radius=_s(2.6) * s, fill=(255, 255, 255))
    pom_r = _s(3.6) * s
    d.ellipse([tip_x - pom_r, tip_y - pom_r, tip_x + pom_r, tip_y + pom_r], fill=(255, 255, 255))
    d.ellipse([tip_x - pom_r * 0.5, tip_y - pom_r * 0.6, tip_x + pom_r * 0.2, tip_y - pom_r * 0.1], fill=(255, 255, 255))


def _draw_nft_gifts(img: Image.Image, draw: ImageDraw.ImageDraw, gifts: list[dict]):
    """Полка с прикреплёнными NFT-подарками у подножия ёлки."""
    if not gifts:
        return
    shown = gifts[:4]
    card_w, card_h = _s(210), _s(104)
    gap = _s(12)
    if len(shown) > 2:  # компактнее, чтобы 3–4 карточки влезли по ширине
        card_w = _s(186)
    total = len(shown) * card_w + (len(shown) - 1) * gap
    start_x = SW / 2 - total / 2
    base_y = _s(730)

    # Подложка-полка
    shelf = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(shelf).rounded_rectangle(
        [start_x - _s(16), base_y - _s(10), start_x + total + _s(16), base_y + card_h + _s(18)],
        radius=_s(18), fill=(8, 16, 32, 120),
    )
    shelf = shelf.filter(ImageFilter.GaussianBlur(_s(6)))
    img.alpha_composite(shelf)

    title_font = _load_font(int(_s(14)))
    sub_font = _load_font(int(_s(11)))

    def _trim(text: str, font, max_w: float) -> str:
        """Обрезает строку по реальной ширине шрифта."""
        text = str(text)
        if draw.textlength(text, font=font) <= max_w:
            return text
        while text and draw.textlength(text + "…", font=font) > max_w:
            text = text[:-1]
        return text + "…"

    for i, gift in enumerate(shown):
        x0 = start_x + i * (card_w + gap)
        y0 = base_y
        # Карточка с «фольгой» и рамкой
        card = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=_s(14), fill=(18, 28, 50, 235),
                             outline=(253, 224, 71, 210), width=max(1, int(SCALE * 1.5)))
        # Лёгкий блик сверху
        cd.rounded_rectangle([x0 + _s(2), y0 + _s(2), x0 + card_w - _s(2), y0 + card_h * 0.45],
                             radius=_s(12), fill=(255, 255, 255, 16))
        img.alpha_composite(card)

        # Эмодзи-медальон
        _draw_emoji(
            img, draw, x0 + _s(30), y0 + card_h / 2, _s(36),
            gift.get("emoji") or "🎁", gift.get("kind"),
        )

        # Тексты: название, подпись «от …» и сообщение (с обрезкой по ширине)
        text_x = x0 + _s(58)
        text_w = card_w - _s(70)
        title = _trim(gift.get("title") or "NFT-подарок", title_font, text_w)
        draw.text((text_x, y0 + _s(16)), title, font=title_font, fill=(255, 249, 219))
        from_name = _trim(gift.get("from_name") or "друга", sub_font, text_w - _s(18))
        draw.text((text_x, y0 + _s(36)), f"от {from_name}", font=sub_font, fill=(147, 197, 253))
        msg = str(gift.get("message") or "").strip()
        if msg:
            draw.text((text_x, y0 + _s(54)), _trim(msg, sub_font, text_w), font=sub_font, fill=(203, 213, 225))
        # Бейдж-«сертификат»: номер NFT/токена или подпись Telegram
        badge = gift.get("badge")
        if badge is None:
            badge = f"#{gift.get('token_id', 0)}"
        if str(badge).strip():
            draw.text((text_x, y0 + _s(72)), _trim(str(badge), sub_font, text_w),
                      font=sub_font, fill=(120, 140, 170))

    if len(gifts) > len(shown):
        draw.text((SW / 2 - _s(30), base_y + card_h + _s(22)),
                  f"ещё +{len(gifts) - len(shown)}", font=sub_font, fill=(253, 224, 71))


def _draw_crowd(img: Image.Image, draw: ImageDraw.ImageDraw, members: list[dict], count: int):
    """Человечки под ёлкой: до 16 фигурок + бейдж «+N»."""
    if count <= 0:
        return
    ground_y = _s(924)
    if count <= 8:
        per_row, rows = count, 1
    elif count <= 16:
        per_row, rows = (count + 1) // 2, 2
    else:
        per_row, rows = 8, 2
    shown = min(count, per_row * rows)
    total_width = SW * 0.76
    step = total_width / (per_row + 0.6)
    start_x = SW / 2 - (per_row - 1) * step / 2

    for idx in range(shown):
        row = idx // per_row
        col = idx % per_row
        x = start_x + col * step + (step * 0.5 if row % 2 else 0)
        y = ground_y - row * _s(32)
        member = members[idx] if idx < len(members) else {}
        hat = HAT_COLORS[(member.get("user_id") or idx) % len(HAT_COLORS)]
        _draw_person(img, draw, x, y, hat, scale=0.95 if rows == 1 else 0.82)

    if count > shown:
        badge_x, badge_y = SW - _s(76), ground_y - _s(36)
        r = _s(27)
        draw.ellipse([badge_x - r, badge_y - r, badge_x + r, badge_y + r], fill=(250, 204, 21), outline=(180, 120, 8), width=max(1, int(1.6 * SCALE)))
        draw.ellipse([badge_x - r * 0.7, badge_y - r * 0.8, badge_x + r * 0.2, badge_y + r * 0.1], fill=(253, 230, 138))
        font = _load_font(int(_s(21)))
        text = f"+{count - shown}"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((badge_x - (bbox[2] - bbox[0]) / 2, badge_y - (bbox[3] - bbox[1]) / 2 - _s(2)),
                  text, fill=(74, 38, 4), font=font)


# ────────────────────────────────────────────────────────────────────────────
#  Публичная функция
# ────────────────────────────────────────────────────────────────────────────
def generate_tree_image(
    decorations: list[dict],
    title: str = "Новогодняя ёлка",
    members: list[dict] | None = None,
    gifts: list[dict] | None = None,
) -> bytes:
    """PNG открытки: текстурированная ёлка, объёмные игрушки и человечки-участники."""
    img = Image.new("RGBA", (SW, SH), BG_TOP + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    _draw_background(img, draw)
    _draw_ground(img, draw)
    _draw_tree(img, draw)

    # Игрушки (по порядку добавления — сверху свежие)
    for dec in decorations:
        otype = dec.get("ornament_type", "ball")
        color_name = dec.get("color", "red")
        color_hex = ORNAMENTS.get(otype, {}).get("colors", {}).get(color_name, "#e63946")
        x = _s(float(dec.get("x", 50)) / 100 * W)
        y = _s(float(dec.get("y", 50)) / 100 * H)
        fn = DRAWERS.get(otype, _draw_ball)
        fn(img, draw, x, y, color_hex)

    _draw_snowfall(draw)
    _draw_nft_gifts(img, draw, gifts or [])
    _draw_crowd(img, draw, members or [], len(members or []))

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(out, "RGBA")

    # Подпись: мягкая тень + градиентная плашка для читаемости
    font = _load_font(30)
    title = str(title or "").strip()
    if title and not title.lower().startswith(("ёлка", "елка", "christmas")):
        title = f"Ёлка: {title}"
    text = title if len(title) <= 46 else title[:45] + "…"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = W / 2
    ty = H - 52
    plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    pd.rounded_rectangle([cx - tw / 2 - 18, ty - 8, cx + tw / 2 + 18, ty + th + 12], radius=16, fill=(6, 12, 26, 150))
    plate = plate.filter(ImageFilter.GaussianBlur(3))
    out.alpha_composite(plate) if out.mode == "RGBA" else out.paste(plate, (0, 0), plate)
    d.text((cx - tw / 2 + 1, ty + 2), text, fill=(0, 0, 0, 140), font=font)
    d.text((cx - tw / 2, ty), text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
