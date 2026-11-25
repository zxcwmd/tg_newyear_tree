"""Генерация новогодней открытки (Pillow): текстурированная ёлка, объёмные игрушки, участники.

Рисуем в 2× разрешении и уменьшаем — так края и мелкие детали выглядят гладко.
"""
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

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


def _vgrad(size, stops, horizontal=False) -> Image.Image:
    """Быстрый линейный градиент: рисуем полоску 1×256 и растягиваем ресайзом.

    Построчный цикл по 2250 точкам на питоне заметно тормозил рендер,
    а resize делает ту же работу в C. stops — [(t, (r, g, b)), ...].
    """
    w, h = size
    ramp = Image.new("RGB", (256, 1) if horizontal else (1, 256))
    rd = ImageDraw.Draw(ramp)
    span = 256
    for i in range(span):
        t = i / (span - 1)
        col = stops[-1][1]
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t <= t1 or j == len(stops) - 2:
                k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                col = _mix(c0, c1, min(1.0, max(0.0, k)))
                break
        if horizontal:
            rd.point((i, 0), fill=col)
        else:
            rd.point((0, i), fill=col)
    return ramp.resize((w, h), Image.BICUBIC)


def _blur_region(img: Image.Image, box, radius: float, extra: float = 0) -> Image.Image:
    """Размывает только окрестность box и возвращает полноразмерный слой.

    GaussianBlur по всему холсту 4500×2250 — главный тормоз рендера: 48 таких
    проходов по пустым областям давали секунды. Здесь blur считается по
    небольшому фрагменту, а результат возвращается на своё место.
    """
    x0 = max(0, int(box[0] - extra - radius * 3))
    y0 = max(0, int(box[1] - extra - radius * 3))
    x1 = min(SW, int(box[2] + extra + radius * 3) + 1)
    y1 = min(SH, int(box[3] + extra + radius * 3) + 1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    crop = img.crop((x0, y0, x1, y1)).convert("RGBA")
    alpha = crop.getchannel("A")
    # Размывать RGBA «как есть» нельзя: в прозрачных пикселях RGB=0, и blur
    # подмешивает чёрный — вокруг светлых слоёв появляется грязный ореол
    # (именно он давал серые кольца на снегу). Поэтому сначала подкладываем
    # под слой его собственный средний цвет, потом размываем цвет и альфу.
    try:
        mean = ImageStat.Stat(crop.convert("RGB"), alpha).mean
    except Exception:
        mean = [255, 255, 255]
    if alpha.getextrema()[1] == 0:
        return Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    base = Image.new("RGBA", crop.size, (int(mean[0]), int(mean[1]), int(mean[2]), 255))
    filled = Image.alpha_composite(base, crop).filter(ImageFilter.GaussianBlur(radius))
    filled.putalpha(alpha.filter(ImageFilter.GaussianBlur(radius)))
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    layer.paste(filled, (x0, y0))
    return layer


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


def _s(v: float) -> float:
    """Пересчёт координат из итогового масштаба в рабочее разрешение."""
    return v * SCALE


# ────────────────────────────────────────────────────────────────────────────
#  Фон и сцена
# ────────────────────────────────────────────────────────────────────────────
def _draw_background(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Звёздное небо с градиентом, сиянием и мягкими сугробами."""
    # Гладкий градиент по четырём опорным цветам — небо не «полосит»
    stops = [
        (0.00, (7, 11, 26)),
        (0.32, (14, 24, 52)),
        (0.62, (24, 44, 82)),
        (0.84, (39, 72, 112)),
        (1.00, (52, 92, 134)),
    ]
    img.paste(_vgrad((SW, SH), [(t, c) for t, c in stops]), (0, 0))

    # Млечный Путь: диагональная полоса из мелкой звёздной пыли
    milky = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    md0 = ImageDraw.Draw(milky)
    rnd_mw = random.Random(101)
    for _ in range(2600):
        tt = rnd_mw.uniform(-0.2, 1.2)
        bx = tt * SW
        by = SH * 0.12 + tt * SH * 0.42
        spread = rnd_mw.gauss(0, SH * 0.085)
        rr = abs(rnd_mw.gauss(0, 1)) * 1.5 + 0.3
        md0.ellipse([bx - rr, by + spread - rr, bx + rr, by + spread + rr],
                    fill=(226, 234, 255, rnd_mw.randint(14, 48)))
    milky = _blur_region(milky, (0, 0, SW, SH * 0.62), _s(1.1))
    img.alpha_composite(milky)
    # мягкое свечение самой полосы — звёздная пыль сливается в дымку
    dust = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dust)
    for i in range(14):
        tt = i / 13
        dd.ellipse([tt * SW - SW * 0.22, SH * 0.12 + tt * SH * 0.42 - SH * 0.12,
                    tt * SW + SW * 0.22, SH * 0.12 + tt * SH * 0.42 + SH * 0.12],
                   fill=(150, 174, 226, 16))
    dust = _blur_region(dust, (0, 0, SW, SH * 0.72), _s(30))
    img.alpha_composite(dust)

    # Дальние звёзды: разные оттенки — голубые, белые, тёплые
    rnd = random.Random(7)
    tints = [(196, 220, 255), (255, 255, 255), (255, 238, 206), (214, 208, 255)]
    for _ in range(300):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH * 0.82)
        r = rnd.uniform(0.6, 1.9) * SCALE
        a = rnd.randint(45, 165)
        tint = tints[rnd.randrange(len(tints))]
        draw.ellipse([x - r, y - r, x + r, y + r], fill=tint + (a,))

    # Крупные звёзды: тёплое ядро + крестик-блик + ореол.
    # Ореолы копим на одном слое — один blur вместо 26 полноразмерных.
    big_stars = [(rnd.uniform(0, SW), rnd.uniform(0, SH * 0.64), rnd.uniform(1.7, 3.4) * SCALE)
                 for _ in range(26)]
    halo_layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    hld = ImageDraw.Draw(halo_layer)
    for x, y, r in big_stars:
        hld.ellipse([x - r * 4.2, y - r * 4.2, x + r * 4.2, y + r * 4.2], fill=(198, 222, 255, 40))
    halo_layer = _blur_region(halo_layer, (0, 0, SW, SH * 0.66), _s(4.5))
    img.alpha_composite(halo_layer)
    for x, y, r in big_stars:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 232))
        draw.ellipse([x - r * 0.5, y - r * 0.5, x + r * 0.5, y + r * 0.5], fill=(255, 255, 255, 255))
        arm = r * 3.0
        draw.line([(x - arm, y), (x + arm, y)], fill=(216, 234, 255, 96), width=max(1, int(SCALE)))
        draw.line([(x, y - arm), (x, y + arm)], fill=(216, 234, 255, 96), width=max(1, int(SCALE)))

    # Северное сияние — размытое цветное пятно
    aurora = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aurora)
    ad.ellipse([-_s(120), _s(30), SW * 0.72, _s(300)], fill=(16, 185, 129, 52))
    ad.ellipse([SW * 0.35, _s(-40), SW + _s(120), _s(240)], fill=(56, 189, 248, 46))
    ad.ellipse([SW * 0.2, _s(90), SW * 0.95, _s(330)], fill=(168, 85, 247, 34))
    aurora = _blur_region(aurora, (-_s(120), 0, SW, _s(340)), _s(46))
    img.alpha_composite(aurora)

    # Луна с мягким гало
    moon = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    md = ImageDraw.Draw(moon)
    mx, my, mr = _s(680), _s(96), _s(34)
    # Гало вложенными кругами: ровный тёплый ореол без «ступеньки» на краю
    for i in range(26, 0, -1):
        t = i / 26
        rr = mr * (1.02 + 1.5 * t)
        a = int(26 * (1 - t) ** 1.8)
        if a > 0:
            md.ellipse([mx - rr, my - rr, mx + rr, my + rr], fill=(255, 232, 150, a))
    moon = _blur_region(moon, (mx - mr * 2.7, my - mr * 2.7, mx + mr * 2.7, my + mr * 2.7), _s(10))
    img.alpha_composite(moon)
    # Тело луны: мягкое затемнение к краю (иначе диск выглядит плоской наклейкой)
    for i in range(int(mr), 0, -1):
        t = i / mr
        col = _mix((255, 252, 221), (248, 222, 158), t ** 2.2)
        draw.ellipse([mx - i, my - i, mx + i, my + i], fill=col)
    # Мягкий блик
    gloss = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse(
        [mx - mr * 0.85, my - mr * 0.9, mx - mr * 0.05, my - mr * 0.02], fill=(255, 255, 255, 70)
    )
    gloss = _blur_region(gloss, (mx - mr, my - mr, mx + mr, my + mr), _s(6))
    img.alpha_composite(gloss)
    # Кратеры: мягкие пятна с подсвеченной кромкой (без чёрных «дырок»)
    craters = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    cd = ImageDraw.Draw(craters)
    rnd_cr = random.Random(55)
    for dx, dy, rr in ((-0.34, 0.18, 0.22), (0.2, -0.28, 0.15), (0.36, 0.34, 0.1),
                       (-0.08, 0.52, 0.08), (-0.5, -0.2, 0.09), (0.05, 0.1, 0.06)):
        cxx, cyy, cr = mx + mr * dx, my + mr * dy, mr * rr
        cd.ellipse([cxx - cr, cyy - cr * 1.02, cxx + cr, cyy + cr * 1.02], fill=(240, 214, 148, 76))
        # подсветка кромки — рельеф, а не «дырка»
        cd.arc([cxx - cr * 0.96, cyy - cr * 0.96, cxx + cr * 0.96, cyy + cr * 0.96], 155, 335,
               fill=(255, 246, 210, 104), width=max(1, int(_s(1.2))))
    craters = _blur_region(craters, (mx - mr, my - mr, mx + mr, my + mr), _s(2.0))
    img.alpha_composite(Image.composite(craters, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)),
                                       _circle_mask(mx, my, mr * 0.995)))


def _hill(img: Image.Image, base_y: float, amp: float, waves, top_color, bottom_color,
          crest_alpha: int = 0, seed: int = 0):
    """Плавный сугроб: синусоидальный силуэт + вертикальный градиент + блик на гребне.

    waves — список (амплитуда, частота, фаза) для суммы синусов: силуэт получается
    органичным, без заметных «дуг» от наложенных эллипсов.
    """
    rnd = random.Random(seed)
    pts = []
    step = 6 * SCALE
    x = -step * 2
    while x <= SW + step * 2:
        t = x / SW
        y = base_y
        for a, f, ph in waves:
            y += math.sin(t * math.pi * f + ph) * amp * a
        y += math.sin(t * math.pi * 0.7 + rnd.uniform(-0.15, 0.15)) * amp * 0.18
        pts.append((x, y))
        x += step
    poly = pts + [(SW + step * 2, SH + step), (-step * 2, SH + step)]

    # Маску слегка размываем — край сугроба получается мягким, как настоящий снег
    mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(_s(2.2)))

    # Вертикальный градиент: у гребня светлее, ниже — холоднее
    y_top = int(min(p[1] for p in pts))
    grad = Image.new("RGB", (SW, SH), bottom_color)
    h_hill = max(2, SH - max(0, y_top))
    ramp = _vgrad((SW, h_hill), [(0.0, top_color), (0.8, bottom_color), (1.0, bottom_color)])
    grad.paste(ramp, (0, max(0, y_top)))
    img.paste(grad, (0, 0), mask)

    # Блик по кромке сугроба — мягкая светлая линия, повторяющая силуэт
    if crest_alpha:
        crest = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
        ImageDraw.Draw(crest).line(pts, fill=(255, 255, 255, crest_alpha),
                                   width=max(1, int(SCALE * 3.0)))
        crest = crest.filter(ImageFilter.GaussianBlur(_s(5.5)))
        img.alpha_composite(crest)
    return pts


def _draw_ground(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Сугробы с плавными силуэтами, искрами и тенью под ёлкой."""
    # Мягкое холодное свечение у горизонта
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-_s(160), _s(700), SW + _s(160), SH + _s(140)], fill=(148, 197, 255, 46))
    glow = _blur_region(glow, (0, _s(680), SW, SH), _s(40))
    img.alpha_composite(glow)

    # Дальний сугроб: холодный, уходит в дымку горизонта
    _hill(
        img, _s(866), _s(30),
        [(1.0, 0.85, 0.4), (0.5, 2.0, 2.1), (0.22, 3.7, 1.1)],
        (222, 234, 250), (206, 222, 244), crest_alpha=48, seed=3,
    )
    # Дымка на стыке неба и снега
    haze = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(haze).ellipse([-_s(200), _s(836), SW + _s(200), SH + _s(40)], fill=(198, 220, 246, 80))
    haze = _blur_region(haze, (0, _s(800), SW, SH), _s(28))
    img.alpha_composite(haze)

    # Средний сугроб: светлее, чуть более выраженный силуэт
    _hill(
        img, _s(944), _s(44),
        [(1.0, 0.65, 2.4), (0.42, 1.7, 0.7), (0.2, 3.1, 1.2)],
        (252, 254, 255), (228, 240, 253), crest_alpha=72, seed=8,
    )
    # Передний сугроб: самый близкий и светлый, с тёплым бликом от луны
    _hill(
        img, _s(1030), _s(52),
        [(1.0, 0.55, 4.1), (0.3, 1.6, 5.3), (0.14, 2.9, 0.2)],
        (255, 255, 255), (238, 246, 255), crest_alpha=96, seed=14,
    )
    moon_glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(moon_glow).ellipse([SW * 0.48, _s(1010), SW * 0.9, _s(1090)], fill=(255, 250, 226, 55))
    moon_glow = _blur_region(moon_glow, (SW * 0.44, _s(990), SW * 0.94, _s(1110)), _s(24))
    img.alpha_composite(moon_glow)

    # Отдельную тень под ёлкой не рисуем: на белом снегу любой эллипс
    # читается грязным кольцом. Объём даёт сам сугроб у ствола.

    # Блёстки на снегу — только вне тени под ёлкой
    rnd = random.Random(21)
    for _ in range(150):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(_s(890), SH)
        if not (SW * 0.30 < x < SW * 0.70 and y < _s(950)):
            r = rnd.uniform(0.8, 2.4) * SCALE
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(120, 230)))


def _draw_snowfall(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Снегопад: дальние мелкие точки + ближние пушистые хлопья с мягким ореолом."""
    rnd = random.Random(33)

    # Дальний план — мелкая крупа, россыпь по всему холсту
    for _ in range(110):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH)
        r = rnd.uniform(0.7, 1.8) * SCALE
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(60, 140)))

    # Ближний план — крупные хлопья с ореолом (мягкое свечение вокруг)
    flakes = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flakes)
    cores = []
    for _ in range(34):
        x = rnd.uniform(0, SW)
        y = rnd.uniform(0, SH * 0.92)
        r = rnd.uniform(2.2, 4.4) * SCALE
        cores.append((x, y, r))
        fd.ellipse([x - r * 1.9, y - r * 1.9, x + r * 1.9, y + r * 1.9], fill=(255, 255, 255, 26))
    flakes = flakes.filter(ImageFilter.GaussianBlur(_s(3)))
    img.alpha_composite(flakes)
    for x, y, r in cores:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(150, 220)))
        # Маленький блик смещён вверх-влево — хлопья выглядят объёмнее
        draw.ellipse([x - r * 0.7, y - r * 0.8, x + r * 0.1, y - r * 0.05], fill=(255, 255, 255, 90))


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
    shadow = _blur_region(shadow, (min(p[0] for p in poly), min(p[1] for p in poly),
                                   max(p[0] for p in poly), max(p[1] for p in poly)), _s(10), _s(8))
    img.alpha_composite(shadow)

    # 2) Маска яруса
    # Маску слегка размываем — край сугроба получается мягким, как настоящий снег
    mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(_s(2.2)))

    # 3) Градиент по вертикали + боковой свет
    # Градиент яруса: светлая кромка сверху -> глубокая тень снизу (через _vgrad)
    h_tier = max(2, int(y1 - y0) + 2)
    ramp = _vgrad((SW, h_tier), [(0.0, _lighten(base_color, 0.26)),
                                 (0.55, _darken(base_color, 0.16)),
                                 (1.0, _darken(base_color, 0.42))])
    grad = Image.new("RGB", (SW, SH), _darken(base_color, 0.42))
    grad.paste(ramp, (0, int(y0)))
    gd = ImageDraw.Draw(grad)
    # Мягкий свет изнутри кроны. Раньше эллипс был прижат к левому краю и
    # обрывался по оси — на ярусе читался светлый «конус» с резкой границей.
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [_s(400) - _s(210), y0 + (y1 - y0) * 0.10, _s(400) + _s(210), y1 + (y1 - y0) * 0.06],
        fill=(255, 255, 255, 34),
    )
    glow = _blur_region(glow, (_s(400) - _s(230), y0, _s(400) + _s(230), y1), _s(52), _s(10))
    img.paste(grad, (0, 0), mask)
    img.alpha_composite(Image.composite(glow, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))

    # 3.2) Боковой свет: слева (луна и звезда) светлее, справа глубже.
    # Без этого ярус читается плоской зелёной заливкой.
    xs_all_ = [q[0] for q in poly]
    cx_l = (min(xs_all_) + max(xs_all_)) / 2
    x_l = max(0, int(min(xs_all_) - _s(20)))
    x_r = min(SW, int(max(xs_all_) + _s(20)))
    w_side = x_r - x_l
    if w_side > 8:
        ramp_light = _vgrad((w_side, 1), [(0.0, (255, 255, 255)), (0.5, (108, 108, 108)),
                                          (1.0, (0, 0, 0))], horizontal=True).convert("L")
        ramp_dark = _vgrad((w_side, 1), [(0.0, (0, 0, 0)), (0.45, (96, 96, 96)),
                                         (1.0, (255, 255, 255))], horizontal=True).convert("L")
        for colour, ramp, amp in ((_lighten(base_color, 0.36), ramp_light, 0.30),
                                  (_darken(base_color, 0.30), ramp_dark, 0.34)):
            layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            ImageDraw.Draw(layer).rectangle([x_l, 0, x_r - 1, SH - 1], fill=colour + (255,))
            alpha_full = Image.new("L", (SW, SH), 0)
            alpha_full.paste(ramp.point(lambda v: int(v * amp)).resize((w_side, SH)), (x_l, 0))
            layer.putalpha(alpha_full)
            img.alpha_composite(Image.composite(layer, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))

    # 3.3) Ветви: поперечные «лапы» с провисом. Дают ярусу структуру —
    # иначе крона выглядит однородным зелёным пятном.
    twig = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    tw = ImageDraw.Draw(twig)
    rows = 9
    height_ = y1 - y0
    for k in range(rows):
        ty = y0 + height_ * (k + 0.55) / rows
        near = [q[0] for q in poly if abs(q[1] - ty) < height_ * 0.03]
        half = (max(near) - min(near)) / 2 if len(near) > 1 else height_ * 0.12
        if half < _s(16):
            continue
        for sgn in (-1.0, 1.0):
            pts = []
            for i in range(9):
                u = i / 8
                pts.append((cx_l + sgn * half * 0.94 * u, ty + height_ * 0.035 * (u ** 1.7)))
            tw.line(pts, fill=_darken(base_color, 0.36) + (58,), width=max(1, int(_s(2.4))))
            tw.line([(px, py - _s(1.7)) for px, py in pts[:7]],
                    fill=_lighten(base_color, 0.24) + (46,), width=max(1, int(_s(1.3))))
    twig = _blur_region(twig, (min(xs_all_), y0, max(xs_all_), y1), _s(1.4))
    img.alpha_composite(Image.composite(twig, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))

    # 3.5) Иглы по контуру: пучки-«лапы», торчащие наружу вдоль силуэта.
    # Рисуем по самим рёбрам полигона (а не случайно), поэтому кромка читается
    # как хвоя, а не как пиксельная крошка после даунскейла.
    needles_out = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    nod = ImageDraw.Draw(needles_out)
    rnd_edge = random.Random(seed + 101)

    def _tuft(px, py, nx, ny, length, width, alpha):
        """Пучок из 2–3 игл с общим основанием — объёмная «лапа»."""
        for k in range(3):
            spread = (k - 1) * 0.42
            ca, sa = math.cos(spread), math.sin(spread)
            dx = nx * ca - ny * sa
            dy = nx * sa + ny * ca
            ln = length * rnd_edge.uniform(0.62, 1.0)
            tip = (px + dx * ln, py + dy * ln)
            half = width * rnd_edge.uniform(0.75, 1.0)
            # перпендикуляр к игле для основания треугольника
            ox, oy = -dy * half, dx * half
            shade = _mix(base_color, (255, 255, 255), rnd_edge.uniform(0.0, 0.22)) \
                if rnd_edge.random() < 0.28 else _darken(base_color, rnd_edge.uniform(0.08, 0.38))
            nod.polygon(
                [(px + ox, py + oy), (px - ox, py - oy), tip],
                fill=shade + (alpha,),
            )

    def _edge_run(p0, p1, outward, count):
        """Иглы вдоль ребра p0→p1, наружу по нормали outward."""
        for i in range(count):
            t = (i + 0.5) / count
            px = p0[0] + (p1[0] - p0[0]) * t
            py = p0[1] + (p1[1] - p0[1]) * t
            jitter = rnd_edge.uniform(-0.22, 0.22)
            nx = outward[0] * math.cos(jitter) - outward[1] * math.sin(jitter)
            ny = outward[0] * math.sin(jitter) + outward[1] * math.cos(jitter)
            seg = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            ln = min(_s(13), max(_s(5), seg * 0.55)) * rnd_edge.uniform(0.75, 1.25)
            _tuft(px, py, nx, ny, ln, _s(2.6), rnd_edge.randint(190, 235))

    cx_est = cx_l
    # Идём по соседним точкам силуэта: нормаль наружу — вбок от центра,
    # у нижней кромки — вниз.
    pts = poly
    n = len(pts)
    for i in range(n - 1):
        p0, p1 = pts[i], pts[i + 1]
        mx = (p0[0] + p1[0]) / 2
        my = (p0[1] + p1[1]) / 2
        dxs = mx - cx_est
        dys = my - y0
        # нормаль наружу: вбок от центра, вниз у нижней кромки
        if abs(dxs) > _s(30):
            outward = (1.0 if dxs > 0 else -1.0, 0.35)
        else:
            outward = (dxs / max(1.0, abs(dxs) + _s(60)), 1.0)
        ln = math.hypot(*outward)
        outward = (outward[0] / ln, outward[1] / ln)
        seg_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        count = max(1, min(6, int(seg_len / _s(11))))
        _edge_run(p0, p1, outward, count)

    needles_out = _blur_region(needles_out, (min(q[0] for q in poly) - _s(20), y0,
                                             max(q[0] for q in poly) + _s(20), y1 + _s(12)), _s(0.35))
    img.alpha_composite(needles_out)

    # 4) Хвоя внутри кроны: короткие штрихи + мягкие вертикальные «ветви»
    rnd = random.Random(seed)
    needles = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    nd = ImageDraw.Draw(needles)
    mpx = mask.load()
    mw, mh = mask.size
    drawn, tries = 0, 0
    while drawn < 1500 and tries < 60000:
        tries += 1
        x = rnd.randint(0, mw - 1)
        y = rnd.randint(max(0, int(y0)), min(mh - 1, int(y1)))
        if mpx[x, y] < 200:
            continue
        drawn += 1
        ang = rnd.uniform(-1.0, 1.0)
        ln = rnd.uniform(2.5, 6.5) * SCALE * 0.55
        col = (255, 255, 255, rnd.randint(10, 24)) if rnd.random() < 0.35 else (7, 46, 28, rnd.randint(10, 22))
        nd.line(
            [(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln + ln * 0.8)],
            fill=col, width=max(1, int(SCALE * 1.1)),
        )
    img.alpha_composite(Image.composite(needles, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), mask))  # noqa: E501

    # 5) Снежные шапки на кончиках «лап» — по локальным выступам силуэта.
    # Вдоль зубцов снег не тянем: сплошная линия по зигзагу читается как
    # белая «молния». Шапка на кончике лапы выглядит естественно.
    snow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(snow)
    xs_all = [q[0] for q in poly]
    left_edge, right_edge = min(xs_all), max(xs_all)
    # точки-выступы: локальные максимумы |x - cx| по вертикали
    tips = []
    for idx in range(1, len(poly) - 1):
        x0_, y0_ = poly[idx - 1]
        x1_, y1_ = poly[idx]
        x2_, y2_ = poly[idx + 1]
        if y1_ < y0 + (y1 - y0) * 0.08:
            continue
        d0, d1, d2 = abs(x0_ - cx_est), abs(x1_ - cx_est), abs(x2_ - cx_est)
        if d1 >= d0 and d1 >= d2 and d1 > (right_edge - left_edge) * 0.16:
            tips.append((x1_, y1_))

    rnd.shuffle(tips)
    for ti, (tx, ty) in enumerate(tips):
        # не на каждой лапе: половина лап остаётся «голой», так снег выглядит естественно
        if ti % 3 == 2:
            continue
        inward = -1.0 if tx > cx_est else 1.0
        tx += inward * rnd.uniform(0.5, 3.0) * SCALE * 0.6
        ty -= rnd.uniform(0.5, 2.0) * SCALE * 0.6
        # Шапка не один ком, а 2–3 «доли»: так снег лежит на лапе неровно.
        cap_w = rnd.uniform(9.0, 13.0) * SCALE * 0.62
        cap_h = cap_w * rnd.uniform(0.40, 0.52)
        lobes = [(0.0, 0.0, 1.0)]
        if rnd.random() < 0.72:
            lobes.append((inward * rnd.uniform(0.7, 1.25) * cap_w,
                          cap_h * rnd.uniform(0.15, 0.45), rnd.uniform(0.55, 0.78)))
        if rnd.random() < 0.45:
            lobes.append((-inward * rnd.uniform(0.45, 0.95) * cap_w,
                          cap_h * rnd.uniform(0.1, 0.4), rnd.uniform(0.45, 0.65)))
        # мягкая синеватая тень под всей шапкой
        for dx, dy, k in lobes:
            sd.ellipse([tx + dx - cap_w * 1.05 * k, ty + dy - cap_h * 0.1 * k,
                        tx + dx + cap_w * 1.05 * k, ty + dy + cap_h * 1.45 * k],
                       fill=(172, 200, 232, 96))
        for dx, dy, k in lobes:
            sd.ellipse([tx + dx - cap_w * k, ty + dy - cap_h * 0.62 * k,
                        tx + dx + cap_w * k, ty + dy + cap_h * 0.62 * k],
                       fill=(250, 253, 255, 247))
            # светлая кромка сверху: снег подсвечен небом
            sd.ellipse([tx + dx - cap_w * 0.72 * k, ty + dy - cap_h * 0.86 * k,
                        tx + dx + cap_w * 0.34 * k, ty + dy + cap_h * 0.02 * k],
                       fill=(255, 255, 255, 240))
    # Снег внутри кроны: шапки на ветках по всей площади, иначе снег есть
    # только по силуэту и крона читается «голой» посередине.
    mpx_snow = mask.load()
    placed = 0
    tries_snow = 0
    while placed < 52 and tries_snow < 20000:
        tries_snow += 1
        px_ = rnd.uniform(left_edge + _s(6), right_edge - _s(6))
        py_ = rnd.uniform(y0 + (y1 - y0) * 0.18, y1 - _s(3))
        if mpx_snow[int(px_), int(py_)] < 235:
            continue
        placed += 1
        w_ = rnd.uniform(3.6, 6.4) * SCALE * 0.58
        h_ = w_ * rnd.uniform(0.34, 0.5)
        sd.ellipse([px_ - w_ * 1.12, py_ - h_ * 0.3, px_ + w_ * 1.12, py_ + h_ * 1.0],
                   fill=(168, 196, 230, 80))
        sd.ellipse([px_ - w_, py_ - h_ * 0.5, px_ + w_, py_ + h_ * 0.55],
                   fill=(246, 251, 255, 215))
        sd.ellipse([px_ - w_ * 0.8, py_ - h_ * 0.7, px_ + w_ * 0.35, py_ + h_ * 0.1],
                   fill=(255, 255, 255, 246))
    # снежная пыль внутри кроны — очень редкая, чтобы не было «ряби»
    for _ in range(34):
        x = rnd.uniform(left_edge, right_edge)
        y = rnd.uniform(y0 + (y1 - y0) * 0.4, y1)
        rr = rnd.uniform(0.9, 1.9) * SCALE
        sd.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, rnd.randint(90, 170)))
    snow = _blur_region(snow, (min(q[0] for q in poly), y0, max(q[0] for q in poly), y1), _s(1.0), _s(10))
    # Шапки лежат НА лапах, поэтому не обрезаем их маской — иначе они
    # срезаются по зубцам и выглядят как обрывки.
    img.alpha_composite(snow)


def _draw_trunk(img: Image.Image, draw: ImageDraw.ImageDraw):
    """Ствол с текстурой коры и снегом у основания."""
    x0, x1 = _s(366), _s(434)
    y0, y1 = _s(800), _s(936)
    # Основа ствола: вертикальный градиент (вверху темнее — там крона тенью)
    trunk = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    # Заливка должна покрывать весь bbox маски (включая расширение у земли):
    # иначе за краем прямоугольника остаются пиксели с RGB=0 и дают тёмную кайму.
    bx0, by0 = int(x0 - _s(2)), int(y0)
    bx1, by1 = int(x1 + _s(2)), int(y1 + _s(2))
    ramp = _vgrad((max(2, bx1 - bx0), max(2, by1 - by0)),
                  [(0.0, _darken(TRUNK, 0.24)),
                   (0.55, _mix(TRUNK, _lighten(TRUNK, 0.30), 0.4)),
                   (1.0, _mix(TRUNK, _lighten(TRUNK, 0.30), 0.6))]).convert("RGBA")
    trunk.paste(ramp, (bx0, by0))
    trunk_mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(trunk_mask).rounded_rectangle([x0, y0, x1, y1], radius=_s(9), fill=255)
    trunk.putalpha(trunk_mask)
    img.alpha_composite(trunk)

    # Кора: изогнутые вертикальные борозды + светящиеся рубцы
    rnd = random.Random(5)
    for _ in range(34):
        xx = rnd.uniform(x0 + _s(5), x1 - _s(5))
        yy = rnd.uniform(y0 + _s(6), y1 - _s(16))
        # Борозда не должна вылезать за низ ствола: иначе тёмные штрихи
        # висят на снегу под стволом.
        ln = min(rnd.uniform(_s(10), _s(38)), max(_s(6), y1 - _s(6) - yy))
        bend = rnd.uniform(-_s(2.5), _s(2.5))
        dark = rnd.random() < 0.62
        col = _darken(TRUNK, rnd.uniform(0.30, 0.58)) if dark else _lighten(TRUNK, rnd.uniform(0.16, 0.34))
        alpha = rnd.randint(150, 235)
        draw.line([(xx, yy), (xx + bend, yy + ln * 0.5), (xx + bend * 1.6, yy + ln)],
                  fill=col + (alpha,), width=max(1, int(rnd.uniform(1.0, 2.6) * SCALE)), joint="curve")
    # Объём и цилиндрическая тень: блик слева, глубокая тень справа
    sheen = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle(
        [x0 + _s(5), y0 + _s(4), x0 + _s(21), y1 - _s(6)], radius=_s(8), fill=(236, 196, 148, 62)
    )
    sheen = _blur_region(sheen, (x0, y0, x1, y1), _s(4))
    img.alpha_composite(sheen)
    shade = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rounded_rectangle(
        [x1 - _s(22), y0, x1 - _s(3), y1], radius=_s(8), fill=(28, 16, 6, 132)
    )
    shade = _blur_region(shade, (x0, y0, x1, y1), _s(4.5))
    img.alpha_composite(shade)
    # Тень ствола, уходящая в крону — ствол «входит» в ёлку, а не обрезан
    top_shade = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(top_shade).ellipse(
        [x0 - _s(26), y0 - _s(30), x1 + _s(26), y0 + _s(26)], fill=(6, 20, 12, 110)
    )
    top_shade = _blur_region(top_shade, (x0 - _s(30), y0 - _s(34), x1 + _s(30), y0 + _s(30)), _s(11))
    img.alpha_composite(top_shade)

    # Снег у основания: ствол «тонет» в снегу. Никаких тёмных ореолов —
    # иначе сугроб читается серой лужей на фоне белого снега.
    rnd_snow = random.Random(17)
    cx_base = (x0 + x1) / 2

    # Сугроб-«подсыпка» у ствола: совсем низкий и в тон снегу.
    # Любая заметная кромка здесь читается как грязное кольцо на белом.
    mound = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    md = ImageDraw.Draw(mound)
    # Снег лежит ПЕРЕД стволом: нижние сантиметры коры уходят под надув,
    # поэтому ствол не «стоит на пьедестале».
    md.ellipse([cx_base - _s(104), y1 - _s(16), cx_base + _s(104), y1 + _s(14)], fill=(252, 254, 255, 255))
    md.ellipse([cx_base - _s(78), y1 - _s(22), cx_base + _s(60), y1 + _s(6)], fill=(255, 255, 255, 255))
    mound = _blur_region(mound, (cx_base - _s(118), y1 - _s(28), cx_base + _s(118), y1 + _s(22)), _s(7))
    img.alpha_composite(mound)
    # Искры на снегу у ствола
    for _ in range(14):
        sx_ = rnd_snow.uniform(cx_base - _s(88), cx_base + _s(88))
        sy_ = rnd_snow.uniform(y1 - _s(18), y1 + _s(16))
        sr = rnd_snow.uniform(0.7, 1.5) * SCALE
        draw.ellipse([sx_ - sr, sy_ - sr, sx_ + sr, sy_ + sr], fill=(255, 255, 255, 225))


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
    # Зелёная лампочка сливалась с хвоей — её заменил тёплый янтарный оттенок.
    palette = [(255, 214, 102), (244, 63, 94), (56, 189, 248), (253, 164, 175), (192, 132, 252)]
    idx = 0
    for (p0, p1, p2), count in zip(wires, (8, 10, 12)):
        for i in range(count):
            t = (i + 0.5) / count
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
            col = palette[idx % len(palette)]
            r = _s(5.2)
            bd.ellipse([x - r * 2.2, y - r * 2.2, x + r * 2.2, y + r * 2.2], fill=col + (34,))
            # цоколь + стекло капли
            bd.ellipse([x - r * 0.34, y - r * 1.35, x + r * 0.34, y - r * 0.7], fill=(72, 78, 90, 235))
            bd.ellipse([x - r * 0.92, y - r * 0.9, x + r * 0.92, y + r * 1.05], fill=col + (255,))
            bd.ellipse([x - r * 0.30, y - r * 0.60, x + r * 0.30, y - r * 0.02], fill=(255, 255, 255, 235))
            idx += 1
    glow = _blur_region(bulbs, (_s(180), _s(290), _s(620), _s(810)), _s(6), _s(8))
    img.alpha_composite(glow)
    img.alpha_composite(bulbs)

    # Снег по верхнему ярусу: маленькие плотные подушки на «лапах»
    cap = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cap)
    rnd_cap = random.Random(91)
    poly_top = _pine_tier(cx, _s(70), _s(420), _s(152), 7)
    xs_top = [p[0] for p in poly_top]
    top_y = min(p[1] for p in poly_top)
    for px_, py_ in poly_top:
        if py_ < top_y + _s(200) or py_ > top_y + _s(290):
            continue
        if abs(px_ - cx) > (max(xs_top) - min(xs_top)) * 0.40:
            continue
        rr = _s(rnd_cap.uniform(3.2, 5.6))
        cd.ellipse([px_ - rr * 1.15, py_ - rr * 0.6, px_ + rr * 1.15, py_ + rr * 0.7], fill=(208, 228, 249, 160))
        cd.ellipse([px_ - rr, py_ - rr * 0.9, px_ + rr, py_ + rr * 0.5], fill=(252, 254, 255, 244))
        cd.ellipse([px_ - rr * 0.8, py_ - rr * 0.95, px_ + rr * 0.28, py_ - rr * 0.02], fill=(255, 255, 255, 255))
    cap = cap.filter(ImageFilter.GaussianBlur(_s(0.8)))
    img.alpha_composite(cap)

    # Макушка
    _draw_star(img, draw, cx, _s(84), _s(50), STAR_COLOR)


def _draw_star(img: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color):
    """Золотая звезда с огранкой: маска + вертикальный градиент, рёбра и искры."""
    # Сияние: радиальный градиент из вложенных кругов. Один размытый эллипс
    # давал грязно-оливковое пятно на тёмном небе.
    halo = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    halo_steps = 34
    for i in range(halo_steps, 0, -1):
        t = i / halo_steps
        rr = r * (0.94 + 2.55 * t)
        a = int(64 * (1 - t) ** 2.1)
        if a <= 0:
            continue
        hd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 214, 96, a))
    halo = _blur_region(halo, (cx - r * 3.6, cy - r * 3.6, cx + r * 3.6, cy + r * 3.6), _s(7))
    img.alpha_composite(halo)

    tip_radius = [r if i % 2 == 0 else r * 0.44 for i in range(10)]
    tip_angle = [-math.pi / 2 + i * math.pi / 5 for i in range(10)]
    tips = [(cx + tip_radius[i] * math.cos(tip_angle[i]), cy + tip_radius[i] * math.sin(tip_angle[i]))
            for i in range(10)]

    # Тень под звездой: только чтобы оторвать её от неба, без тёмной каймы
    sh = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x + _s(2.0), y + _s(3.0)) for x, y in tips], fill=(120, 72, 8, 70))
    sh = _blur_region(sh, (cx - r * 1.4, cy - r * 1.4, cx + r * 1.4, cy + r * 1.4), _s(2.6))
    img.alpha_composite(sh)

    # Маска звезды + золотой градиент сверху (свет) вниз (тёплая тень)
    star_mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(star_mask).polygon(tips, fill=255)
    grad = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    y_top, y_bot = cy - r * 1.05, cy + r * 1.05
    for yy in range(int(y_top), int(y_bot) + 1):
        t = (yy - y_top) / max(1.0, y_bot - y_top)
        col = _mix((255, 249, 208), _mix(color, _darken(color, 0.18), t), min(1.0, t * 1.15))
        gd.line([(cx - r * 1.3, yy), (cx + r * 1.3, yy)], fill=col + (255,))
    star_layer = Image.composite(grad, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), star_mask)

    # Огранка и блики — на отдельном слое с лёгким размытием: резкие линии
    # по золоту читаются царапинами.
    facets = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    fd = ImageDraw.Draw(facets)
    for i in range(10):
        if i % 2 == 1:
            continue
        a = tip_angle[i]
        vx = cx + r * 0.40 * math.cos(a + math.pi / 5)
        vy = cy + r * 0.40 * math.sin(a + math.pi / 5)
        fd.line([(cx, cy), (vx, vy)], fill=_darken(color, 0.34) + (86,),
                width=max(1, int(_s(1.1))))
    for i in (0, 2):
        a = tip_angle[i]
        ex, ey = tips[i]
        fd.line([(cx + r * 0.06 * math.cos(a - 0.16), cy + r * 0.06 * math.sin(a - 0.16)),
                 (ex - r * 0.24 * math.cos(a), ey - r * 0.24 * math.sin(a))],
                fill=(255, 238, 160, 126), width=max(1, int(_s(2.6))))
    facets = _blur_region(facets, (cx - r * 1.2, cy - r * 1.2, cx + r * 1.2, cy + r * 1.2), _s(1.1))
    facets = Image.composite(facets, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), star_mask)
    star_layer = Image.alpha_composite(star_layer, facets)
    img.alpha_composite(star_layer)

    # Контур и рёбра — резкие, поверх гладкой заливки
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon(tips, outline=_darken(color, 0.30) + (235,))

    # Блики: короткий штрих по верхнему лучу и мягкое свечение у кончика
    d.line([(cx - r * 0.03, cy - r * 0.46), (cx + r * 0.02, cy - r * 0.30)],
           fill=(255, 253, 234, 190), width=max(1, int(_s(1.6))))
    glint = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd2 = ImageDraw.Draw(glint)
    gx, gy = cx, cy - r * 1.02
    for i in range(10, 0, -1):
        t = i / 10
        rr = r * (0.10 + 0.34 * t)
        gd2.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], fill=(255, 250, 214, int(30 * (1 - t) ** 1.5)))
    glint = _blur_region(glint, (gx - r * 0.5, gy - r * 0.5, gx + r * 0.5, gy + r * 0.5), _s(2.5))
    img.alpha_composite(glint)

    # Искры-лучики вокруг
    spark = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(spark)
    for dx, dy, ln in ((-1.5, -0.55, 0.5), (1.4, -0.7, 0.4), (-0.95, 1.2, 0.32), (1.1, 1.0, 0.28)):
        sx, sy = cx + dx * r, cy + dy * r
        l = ln * r
        sd.line([(sx - l, sy), (sx + l, sy)], fill=(255, 243, 180, 220), width=max(1, int(_s(1.5))))
        sd.line([(sx, sy - l), (sx, sy + l)], fill=(255, 243, 180, 220), width=max(1, int(_s(1.5))))
    spark = spark.filter(ImageFilter.GaussianBlur(_s(0.6)))
    img.alpha_composite(spark)


# ────────────────────────────────────────────────────────────────────────────
#  Игрушки (объёмные)
# ────────────────────────────────────────────────────────────────────────────
def _hang(draw: ImageDraw.ImageDraw, x: float, y: float, top_y: float):
    """Петелька и ниточка от точки крепления."""
    draw.line([(x, top_y), (x, y - _s(13))], fill=(226, 232, 240, 190), width=max(1, int(1.3 * SCALE)))
    draw.ellipse([x - _s(3), y - _s(16), x + _s(3), y - _s(10)], outline=(250, 204, 21), width=max(1, int(1.4 * SCALE)))


def _circle_mask(cx: float, cy: float, r: float) -> Image.Image:
    """Круглая маска для клиппинга бликов внутри шара."""
    m = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(m).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return m


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
    # Нижний отражённый свет — мягкое размытое пятно, а не дуга:
    # чёткая дуга по низу читалась как «улыбка» на ёлочном шаре.
    bounce = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(bounce).ellipse(
        [cx - r * 0.66, cy + r * 0.22, cx + r * 0.66, cy + r * 0.86],
        fill=_lighten(rgb, 0.5) + (110,),
    )
    bounce = bounce.filter(ImageFilter.GaussianBlur(_s(2.4)))
    img.alpha_composite(bounce, (0, 0)) if False else img.alpha_composite(
        Image.composite(bounce, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)),
                        _circle_mask(cx, cy, r * 0.94))
    )


def _draw_ball(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(30))
    # мягкая тень на ветке под шаром — предмет «стоит», а не парит
    contact = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(contact).ellipse(
        [x - _s(20), y + _s(14), x + _s(20), y + _s(26)], fill=(8, 26, 16, 90)
    )
    contact = contact.filter(ImageFilter.GaussianBlur(_s(5)))
    img.alpha_composite(contact)
    r = _s(23)
    _radial_ball(img, x, y, r, rgb)
    # Матовое «стекло»: мягкий полумесяц сверху-слева, без резких дуг
    d = ImageDraw.Draw(img, "RGBA")
    sheen = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).ellipse(
        [x - r * 0.86, y - r * 0.95, x + r * 0.05, y - r * 0.05], fill=(255, 255, 255, 128)
    )
    sheen = sheen.filter(ImageFilter.GaussianBlur(_s(1.8)))
    img.alpha_composite(Image.composite(sheen, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)),
                                       _circle_mask(x, y, r * 0.96)))


def _draw_snowflake(img, draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(24))
    d = draw
    glow = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([x - _s(22), y - _s(22), x + _s(22), y + _s(22)], fill=rgb + (70,))
    glow = glow.filter(ImageFilter.GaussianBlur(_s(8)))
    img.alpha_composite(glow)
    r = _s(20)
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
    _hang(draw, x, y, y - _s(28))
    s = _s(19)
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
    _hang(draw, x, y, y - _s(26))
    # Основа колокольчика
    top = y - _s(17)
    bot = y + _s(11)
    for i in range(16, 0, -1):
        t = i / 16
        rr = _s(18) * t
        col = _mix(_lighten(gold, 0.45), _darken(gold, 0.42), 1 - t)
        draw.ellipse([x - rr, top - rr * 0.55, x + rr, bot + rr * 0.28], fill=col)
    draw.polygon([(x - _s(18), y + _s(5)), (x + _s(18), y + _s(5)), (x + _s(20), y + _s(13)), (x - _s(20), y + _s(13))],
                 fill=_darken(gold, 0.24))
    # Ободок и язычок
    draw.rounded_rectangle([x - _s(21), y + _s(9), x + _s(21), y + _s(16)], radius=_s(3.4), fill=_lighten(gold, 0.2))
    draw.ellipse([x - _s(5.6), y + _s(15), x + _s(5.6), y + _s(25)], fill=(150, 104, 10))
    draw.ellipse([x - _s(3.6), y + _s(16.5), x + _s(2.2), y + _s(20.5)], fill=(226, 178, 52))
    # Блик и ручка
    draw.ellipse([x - _s(11), y - _s(14), x - _s(2.5), y + _s(2)], fill=(255, 250, 220, 150))
    draw.ellipse([x - _s(8.5), y - _s(12), x - _s(4.5), y - _s(3)], fill=(255, 253, 235, 210))
    draw.arc([x - _s(8), y - _s(28), x + _s(8), y - _s(15)], 200, 340, fill=_darken(gold, 0.3), width=max(1, int(2.2 * SCALE)))


def _draw_candy(img, draw, x, y, color_hex):
    """Леденец в обёртке: сплюснутый корпус, диагональные полосы, косички-фантики."""
    rgb = _hex_to_rgb(color_hex)
    _hang(draw, x, y, y - _s(24))
    rx, ry = _s(15), _s(11)

    # Фантики-косички по бокам: треугольный веер со складками
    for sx in (-1, 1):
        tip_x = x + sx * _s(30)
        base_x = x + sx * _s(13)
        draw.polygon(
            [(base_x, y - ry * 0.85), (tip_x, y - _s(11)), (tip_x + sx * _s(2), y - _s(2)),
             (tip_x + sx * _s(2), y + _s(3)), (tip_x, y + _s(11)), (base_x, y + ry * 0.85)],
            fill=_lighten(rgb, 0.28), outline=_darken(rgb, 0.22),
        )
        # складки фантика — три коротких луча от основания к краю
        for k, fy in enumerate((-0.62, 0.0, 0.62)):
            draw.line(
                [(base_x, y + ry * fy * 0.8), (x + sx * _s(26), y + _s(8) * fy)],
                fill=_darken(rgb, 0.10 + 0.06 * k), width=max(1, int(_s(1.1))),
            )

    # Корпус: сплюснутый овал с радиальным объёмом
    for i in range(14, 0, -1):
        t = i / 14
        col = _mix(_lighten(rgb, 0.42), _darken(rgb, 0.34), t ** 0.85)
        draw.ellipse([x - rx * t, y - ry * t, x + rx * t, y + ry * t], fill=col)

    # Диагональные полосы (клиппим овалом): классическая карамель
    stripes = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for off in range(-4, 5):
        ox = off * _s(9)
        sd.line([(x + ox - _s(26), y - _s(20)), (x + ox + _s(26), y + _s(20))],
                fill=_lighten(rgb, 0.72) + (170,), width=max(2, int(_s(3.2))))
    oval_mask = Image.new("L", (SW, SH), 0)
    ImageDraw.Draw(oval_mask).ellipse([x - rx * 0.98, y - ry * 0.98, x + rx * 0.98, y + ry * 0.98], fill=255)
    img.alpha_composite(Image.composite(stripes, Image.new("RGBA", (SW, SH), (0, 0, 0, 0)), oval_mask))

    d = ImageDraw.Draw(img, "RGBA")
    # контур + блик
    d.ellipse([x - rx, y - ry, x + rx, y + ry], outline=_darken(rgb, 0.3), width=max(1, int(_s(1.1))))
    d.ellipse([x - rx * 0.62, y - ry * 0.78, x - rx * 0.06, y - ry * 0.22], fill=(255, 255, 255, 205))
    d.ellipse([x - rx * 0.50, y - ry * 0.66, x - rx * 0.26, y - ry * 0.44], fill=(255, 255, 255, 245))


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
    # Валенки: два мягких овала под подолом
    for sx in (-1, 1):
        d.ellipse([cx + sx * _s(4.6) * s - _s(4.4) * s, bottom - _s(1.2) * s,
                   cx + sx * _s(4.6) * s + _s(4.4) * s, bottom + _s(3.4) * s],
                  fill=(96, 62, 40))
        d.ellipse([cx + sx * _s(4.6) * s - _s(3.4) * s, bottom - _s(0.6) * s,
                   cx + sx * _s(4.6) * s + _s(1.0) * s, bottom + _s(1.6) * s],
                  fill=(132, 92, 62))
    d.rounded_rectangle([cx - half * 0.9, top, cx + half * 0.9, top + _s(3.4) * s], radius=_s(1.8) * s, fill=(248, 250, 252))
    # Шарфик с развевающимся концом — сразу читается «зимний персонаж»
    scarf_y = top + _s(4.0) * s
    d.rounded_rectangle([cx - half - _s(2.6) * s, scarf_y, cx + half + _s(2.6) * s, scarf_y + _s(4.2) * s],
                        radius=_s(2.0) * s, fill=_darken(hat_rgb, 0.12))
    d.rounded_rectangle([cx - half - _s(2.6) * s, scarf_y, cx + half + _s(2.6) * s, scarf_y + _s(1.6) * s],
                        radius=_s(1.2) * s, fill=_lighten(hat_rgb, 0.18))
    # свисающий конец шарфа
    d.polygon([(cx + half * 0.35, scarf_y + _s(3) * s),
               (cx + half * 1.25, scarf_y + _s(11) * s),
               (cx + half * 1.55, scarf_y + _s(9) * s),
               (cx + half * 0.72, scarf_y + _s(2) * s)],
              fill=_darken(hat_rgb, 0.2))
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
        _draw_person(img, draw, x, y, hat, scale=1.16 if rows == 1 else 0.98)

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

    _draw_snowfall(img, draw)
    _draw_crowd(img, draw, members or [], len(members or []))

    out = img.convert("RGB").resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(out, "RGBA")

    # Подпись: тёмно-синяя «лента» с золотой окантовкой и мягким свечением.
    font = _load_font(32)
    title = str(title or "").strip()
    if title and not title.lower().startswith(("ёлка", "елка", "christmas")):
        title = f"Ёлка: {title}"
    text = title if len(title) <= 46 else title[:45] + "…"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = W / 2
    # Лента должна целиком помещаться в холст: считаем её низ и поднимаем при нужде
    ty = H - 60
    if ty + th + 18 > H - 6:
        ty = H - th - 24
    plate_box = [cx - tw / 2 - 34, ty - 14, cx + tw / 2 + 34, ty + th + 16]

    # ореол вокруг ленты — она читается на любом фоне
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).rounded_rectangle(
        [plate_box[0] - 6, plate_box[1] - 6, plate_box[2] + 6, plate_box[3] + 6],
        radius=26, fill=(255, 214, 120, 40),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(9))
    out.paste(halo, (0, 0), halo)

    plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    # заливка-градиент по вертикали внутри «ленты»
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    h_plate = max(2, int(plate_box[3] - plate_box[1]) + 1)
    ramp = _vgrad((int(plate_box[2] - plate_box[0]) + 1, h_plate),
                  [(0.0, (13, 26, 48)), (1.0, (7, 14, 30))]).convert("RGBA")
    ramp.putalpha(225)
    grad.paste(ramp, (int(plate_box[0]), int(plate_box[1])))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(plate_box, radius=22, fill=255)
    plate.alpha_composite(Image.composite(grad, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))
    pd.rounded_rectangle(plate_box, radius=22, outline=(255, 206, 84, 210), width=2)
    pd.rounded_rectangle([plate_box[0] + 4, plate_box[1] + 4, plate_box[2] - 4, plate_box[3] - 4],
                         radius=18, outline=(255, 236, 170, 90), width=1)
    out.paste(plate, (0, 0), plate)

    # золотое свечение под текстом
    tglow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(tglow).text((cx - tw / 2, ty), text, fill=(255, 205, 90, 160), font=font)
    tglow = tglow.filter(ImageFilter.GaussianBlur(4))
    out.paste(tglow, (0, 0), tglow)
    d.text((cx - tw / 2, ty), text, fill=(255, 250, 236, 255), font=font)
    # снежинки по бокам ленты
    for sx_ in (-1, 1):
        bx = cx + sx_ * (tw / 2 + 18)
        by = ty + th * 0.55
        for ang in range(0, 180, 60):
            ra = math.radians(ang)
            d.line([(bx - math.cos(ra) * 7, by - math.sin(ra) * 7),
                    (bx + math.cos(ra) * 7, by + math.sin(ra) * 7)],
                   fill=(255, 216, 120, 220), width=1)
        d.ellipse([bx - 1.4, by - 1.4, bx + 1.4, by + 1.4], fill=(255, 240, 190, 255))

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
