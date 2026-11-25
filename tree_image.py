"""Генерация картинки ёлки с Pillow."""
import io
import math
from PIL import Image, ImageDraw, ImageFont
from config import ORNAMENTS

W, H = 800, 1000

# Цвета
BG_TOP = (15, 23, 42)
BG_BOTTOM = (30, 58, 95)
TREE_GREEN = (22, 101, 52)
TREE_GREEN_LIGHT = (34, 139, 74)
TREE_GREEN_DARK = (15, 80, 40)
TRUNK = (101, 67, 33)
STAR_COLOR = (255, 214, 10)


def _hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _load_font(size: int):
    # Пробуем системные шрифты, иначе дефолтный
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_background(draw: ImageDraw.ImageDraw):
    # Вертикальный градиент
    for y in range(H):
        t = y / H
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    # Снежинки-фон (случайные точки)
    import random
    random.seed(42)
    for _ in range(80):
        x = random.randint(0, W)
        y = random.randint(0, H)
        r = random.randint(1, 3)
        alpha = random.randint(60, 160)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, alpha))


def _draw_tree(draw: ImageDraw.ImageDraw):
    cx = W // 2
    # Ствол
    draw.rectangle([cx - 30, 820, cx + 30, 900], fill=TRUNK)
    # Три яруса ёлки (треугольники)
    tiers = [
        (cx, 120, 180, 420),   # верх
        (cx, 300, 260, 640),   # середина
        (cx, 480, 340, 860),   # низ
    ]
    for i, (x, top, half_w, bottom) in enumerate(tiers):
        color = TREE_GREEN if i % 2 == 0 else TREE_GREEN_LIGHT
        draw.polygon([(x, top), (x - half_w, bottom), (x + half_w, bottom)], fill=color)
        # Тёмная окантовка снизу
        draw.line([(x - half_w, bottom), (x + half_w, bottom)], fill=TREE_GREEN_DARK, width=4)
    # Звезда на макушке
    _draw_star(draw, cx, 100, 55, STAR_COLOR)


def _draw_star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color):
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        points.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
    draw.polygon(points, fill=color, outline=(200, 160, 0))


def _draw_ball(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    r = 18
    draw.ellipse([x - r, y - r, x + r, y + r], fill=rgb, outline=(0, 0, 0, 60), width=2)
    # Блик
    draw.ellipse([x - 7, y - 8, x + 2, y + 1], fill=(255, 255, 255, 180))
    # Крепление
    draw.rectangle([x - 4, y - r - 6, x + 4, y - r], fill=(180, 180, 180))


def _draw_snowflake(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    r = 16
    for angle in range(0, 360, 60):
        rad = math.radians(angle)
        x2 = x + r * math.cos(rad)
        y2 = y + r * math.sin(rad)
        draw.line([(x, y), (x2, y2)], fill=rgb, width=3)
        # Веточки
        for t in (0.5, 0.8):
            bx = x + r * t * math.cos(rad)
            by = y + r * t * math.sin(rad)
            for da in (-30, 30):
                rad2 = rad + math.radians(da)
                draw.line([(bx, by), (bx + 6 * math.cos(rad2), by + 6 * math.sin(rad2))], fill=rgb, width=2)


def _draw_gift(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    s = 16
    draw.rectangle([x - s, y - s + 6, x + s, y + s], fill=rgb, outline=(0, 0, 0, 80), width=2)
    draw.rectangle([x - s, y - s, x + s, y - s + 8], fill=tuple(min(255, c + 30) for c in rgb))
    # Лента
    draw.rectangle([x - 3, y - s, x + 3, y + s], fill=(255, 215, 0))
    draw.ellipse([x - 8, y - s - 8, x - 1, y - s], fill=(255, 215, 0))
    draw.ellipse([x + 1, y - s - 8, x + 8, y - s], fill=(255, 215, 0))


def _draw_bell(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    # Колокольчик: полусфера + юбка
    draw.pieslice([x - 14, y - 14, x + 14, y + 14], 180, 360, fill=rgb, outline=(0, 0, 0, 80))
    draw.rectangle([x - 14, y, x + 14, y + 6], fill=rgb)
    draw.ellipse([x - 4, y + 6, x + 4, y + 14], fill=(120, 80, 0))
    draw.ellipse([x - 3, y - 18, x + 3, y - 12], fill=rgb)


def _draw_candy(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    # Конфета: круг + обёртка по бокам
    draw.ellipse([x - 10, y - 10, x + 10, y + 10], fill=rgb, outline=(0, 0, 0, 80), width=2)
    draw.polygon([(x - 10, y), (x - 20, y - 8), (x - 20, y + 8)], fill=rgb)
    draw.polygon([(x + 10, y), (x + 20, y - 8), (x + 20, y + 8)], fill=rgb)
    draw.line([(x - 5, y - 7), (x + 5, y + 7)], fill=(255, 255, 255), width=3)


def _draw_angel(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    # Крылышки
    draw.polygon([(x, y), (x - 18, y - 10), (x - 14, y + 6)], fill=(255, 255, 255, 210))
    draw.polygon([(x, y), (x + 18, y - 10), (x + 14, y + 6)], fill=(255, 255, 255, 210))
    # Платье ангелочка
    draw.polygon([(x, y - 4), (x - 11, y + 14), (x + 11, y + 14)], fill=rgb)
    # Голова и нимб
    draw.ellipse([x - 6, y - 14, x + 6, y - 2], fill=(255, 235, 205))
    draw.ellipse([x - 8, y - 19, x + 8, y - 14], outline=(255, 215, 0), width=2)


def _draw_crystal(draw, x, y, color_hex):
    rgb = _hex_to_rgb(color_hex)
    points = [(x, y - 18), (x + 13, y), (x, y + 18), (x - 13, y)]
    draw.polygon(points, fill=rgb, outline=(255, 255, 255), width=2)
    draw.polygon([(x, y - 10), (x + 6, y), (x, y + 10), (x - 6, y)], fill=(255, 255, 255, 180))


HAT_COLORS = [
    (220, 38, 38),    # красная
    (37, 99, 235),    # синяя
    (22, 163, 74),    # зелёная
    (168, 85, 247),   # фиолетовая
    (234, 88, 12),    # оранжевая
    (13, 148, 136),   # бирюзовая
]
SKIN_COLOR = (253, 224, 199)


def _draw_person(draw: ImageDraw.ImageDraw, cx: float, cy: float, hat_rgb, scale: float = 1.0):
    """Маленький человечек в новогодней шапочке (cy — низ ног)."""
    s = scale
    body_w = 13 * s
    body_h = 20 * s
    head_r = 8 * s
    # Тень
    draw.ellipse(
        [cx - 12 * s, cy - 3 * s, cx + 12 * s, cy + 2 * s],
        fill=(2, 6, 23, 90),
    )
    # Туловище (шуба)
    draw.rounded_rectangle(
        [cx - body_w / 2, cy - body_h, cx + body_w / 2, cy - 2 * s],
        radius=4 * s,
        fill=hat_rgb,
    )
    # Меховая опушка
    draw.rounded_rectangle(
        [cx - body_w / 2 - 1 * s, cy - 6 * s, cx + body_w / 2 + 1 * s, cy - 2 * s],
        radius=2 * s,
        fill=(255, 255, 255),
    )
    # Голова
    head_y = cy - body_h - head_r * 0.75
    draw.ellipse(
        [cx - head_r, head_y - head_r, cx + head_r, head_y + head_r],
        fill=SKIN_COLOR,
    )
    # Глазки
    draw.ellipse([cx - 3.4 * s, head_y - 1.5 * s, cx - 1.6 * s, head_y + 0.4 * s], fill=(30, 41, 59))
    draw.ellipse([cx + 1.6 * s, head_y - 1.5 * s, cx + 3.4 * s, head_y + 0.4 * s], fill=(30, 41, 59))
    # Улыбка
    draw.arc(
        [cx - 3 * s, head_y + 0.5 * s, cx + 3 * s, head_y + 4.5 * s],
        start=15, end=165, fill=(120, 53, 15), width=max(1, int(1.4 * s)),
    )
    # Новогодняя шапочка с помпоном
    hat_top = head_y - head_r * 2.1
    draw.polygon(
        [
            (cx - head_r * 1.05, head_y - head_r * 0.55),
            (cx + head_r * 1.05, head_y - head_r * 0.55),
            (cx + head_r * 0.15, hat_top),
        ],
        fill=hat_rgb,
    )
    draw.rounded_rectangle(
        [cx - head_r * 1.12, head_y - head_r * 0.78, cx + head_r * 1.12, head_y - head_r * 0.36],
        radius=2.4 * s,
        fill=(255, 255, 255),
    )
    draw.ellipse(
        [cx + head_r * 0.02, hat_top - 3.6 * s, cx + head_r * 0.75, hat_top + 3.2 * s],
        fill=(255, 255, 255),
    )


def _draw_crowd(draw: ImageDraw.ImageDraw, members: list[dict], count: int):
    """Рисует человечков под ёлкой: до 8 фигурок + бейдж «+N», если участников больше."""
    if count <= 0:
        return
    ground_y = 924
    if count <= 8:
        per_row, rows = count, 1
    elif count <= 16:
        per_row, rows = (count + 1) // 2, 2
    else:
        per_row, rows = 8, 2

    shown = min(count, per_row * rows)
    total_width = W * 0.74
    step = total_width / (per_row + 0.6)
    start_x = W / 2 - (per_row - 1) * step / 2

    for idx in range(shown):
        row = idx // per_row
        col = idx % per_row
        x = start_x + col * step + (step * 0.5 if row % 2 else 0)
        y = ground_y - row * 30
        member = members[idx] if idx < len(members) else {}
        hat = HAT_COLORS[(member.get("user_id") or idx) % len(HAT_COLORS)]
        _draw_person(draw, x, y, hat, scale=0.95 if rows == 1 else 0.8)

    if count > shown:
        badge_x, badge_y = W - 74, ground_y - 34
        draw.ellipse([badge_x - 26, badge_y - 26, badge_x + 26, badge_y + 26], fill=(250, 204, 21))
        font = _load_font(22)
        text = f"+{count - shown}"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (badge_x - (bbox[2] - bbox[0]) / 2, badge_y - (bbox[3] - bbox[1]) / 2 - 3),
            text,
            fill=(69, 26, 3),
            font=font,
        )


DRAWERS = {
    "ball": _draw_ball,
    "star": lambda d, x, y, c: _draw_star(d, x, y, 20, _hex_to_rgb(c)),
    "snowflake": _draw_snowflake,
    "gift": _draw_gift,
    "bell": _draw_bell,
    "candy": _draw_candy,
    "angel": _draw_angel,
    "crystal": _draw_crystal,
}


def generate_tree_image(
    decorations: list[dict],
    title: str = "Новогодняя ёлка",
    members: list[dict] | None = None,
) -> bytes:
    """Генерирует PNG ёлки со всеми игрушками. x,y — относительные 0..100.

    members — участники сбора: под ёлкой рисуются человечки в шапочках.
    """
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img, "RGBA")
    _draw_background(draw)
    _draw_tree(draw)

    for dec in decorations:
        otype = dec.get("ornament_type", "ball")
        color_name = dec.get("color", "red")
        color_hex = ORNAMENTS.get(otype, {}).get("colors", {}).get(color_name, "#e63946")
        x = dec.get("x", 50) / 100 * W
        y = dec.get("y", 50) / 100 * H
        fn = DRAWERS.get(otype, _draw_ball)
        fn(draw, x, y, color_hex)

    # Человечки-участники в шапочках под ёлкой
    _draw_crowd(draw, members or [], len(members or []))

    # Заголовок внизу
    font = _load_font(30)
    text = title
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, H - 44), text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
