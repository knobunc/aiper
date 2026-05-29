"""Render an irrigation zone map as a PNG image."""

from __future__ import annotations

import math
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, ImageColor, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .coordinator import IrriSenseZone

ZONE_COLORS = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
    "#00BCD4", "#F44336", "#8BC34A", "#3F51B5",
]

BG_COLOR = "#f5f5f0"
GRID_COLOR = "#e0e0e0"
ORIGIN_COLOR = "#333333"
POSITION_COLOR = "#FF1744"
LABEL_COLOR = "#333333"
ZONE_FILL_ALPHA = 50

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _rotate(
    x: float, y: float, degrees: float
) -> tuple[float, float]:
    rad = math.radians(degrees)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a


def render_map(
    zones: list[IrriSenseZone],
    position: tuple[int, int] | None = None,
    rotation_degrees: float = 0.0,
    image_size: int = 800,
) -> bytes:
    """Render zone waypoints and live position as a PNG image."""
    all_x: list[float] = [0.0]
    all_y: list[float] = [0.0]

    for zone in zones:
        for pt in zone.points:
            rx, ry = _rotate(pt.x, pt.y, rotation_degrees)
            all_x.append(rx)
            all_y.append(ry)

    if position is not None:
        rx, ry = _rotate(position[0], position[1], rotation_degrees)
        all_x.append(rx)
        all_y.append(ry)

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    span_x = max_x - min_x or 200.0
    span_y = max_y - min_y or 200.0
    span = max(span_x, span_y)

    margin = image_size * 0.08
    usable = image_size - 2 * margin
    scale = usable / span

    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2

    def to_px(wx: float, wy: float) -> tuple[float, float]:
        px = margin + (wx - cx) * scale + usable / 2
        py = margin + (cy - wy) * scale + usable / 2
        return px, py

    img = Image.new("RGBA", (image_size, image_size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    grid_step = 100
    while grid_step * scale < 30:
        grid_step *= 2
    while grid_step * scale > 150:
        grid_step //= 2
    if grid_step < 50:
        grid_step = 50

    grid_min = int(min(min_x, min_y) // grid_step) * grid_step
    grid_max = int(max(max_x, max_y) // grid_step + 1) * grid_step

    for g in range(grid_min, grid_max + grid_step, grid_step):
        gx_start, _ = to_px(g, min_y - span)
        gx_end, _ = to_px(g, max_y + span)
        draw.line([(gx_start, 0), (gx_end, image_size)], fill=GRID_COLOR, width=1)
        _, gy_start = to_px(min_x - span, g)
        _, gy_end = to_px(max_x + span, g)
        draw.line([(0, gy_start), (image_size, gy_end)], fill=GRID_COLOR, width=1)

    for zi, zone in enumerate(zones):
        color = ZONE_COLORS[zi % len(ZONE_COLORS)]
        if not zone.points:
            continue

        origin_px = to_px(*_rotate(0, 0, rotation_degrees))
        rotated = [_rotate(pt.x, pt.y, rotation_degrees) for pt in zone.points]
        pixels = [to_px(rx, ry) for rx, ry in rotated]
        path = [origin_px, *pixels, origin_px]

        rgb = ImageColor.getrgb(color)
        fill_color = (*rgb, ZONE_FILL_ALPHA)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.polygon(path, fill=fill_color)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        draw.line(path, fill=color, width=2)

        r = 5
        for px, py in pixels:
            draw.ellipse([px - r, py - r, px + r, py + r], fill=color)

        cent_x = sum(p[0] for p in pixels) / len(pixels)
        cent_y = sum(p[1] for p in pixels) / len(pixels)
        font = _load_font(12)
        bbox = draw.textbbox((0, 0), zone.name, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(
            (cent_x - tw / 2, cent_y - 20),
            zone.name,
            fill=LABEL_COLOR,
            font=font,
        )

    ox, oy = to_px(0.0, 0.0)
    s = 8
    draw.line([(ox - s, oy), (ox + s, oy)], fill=ORIGIN_COLOR, width=2)
    draw.line([(ox, oy - s), (ox, oy + s)], fill=ORIGIN_COLOR, width=2)
    draw.ellipse([ox - 3, oy - 3, ox + 3, oy + 3], fill=ORIGIN_COLOR)

    if position is not None:
        prx, pry = _rotate(position[0], position[1], rotation_degrees)
        ppx, ppy = to_px(prx, pry)
        pr = 8
        draw.ellipse(
            [ppx - pr, ppy - pr, ppx + pr, ppy + pr],
            fill=POSITION_COLOR,
            outline="#FFFFFF",
            width=2,
        )

    legend_x = margin
    legend_y = image_size - margin
    for zi, zone in enumerate(zones):
        if not zone.points:
            continue
        color = ZONE_COLORS[zi % len(ZONE_COLORS)]
        draw.rectangle(
            [legend_x, legend_y - 12, legend_x + 12, legend_y],
            fill=color,
        )
        font = _load_font(11)
        draw.text(
            (legend_x + 16, legend_y - 13),
            zone.name,
            fill=LABEL_COLOR,
            font=font,
        )
        bbox = draw.textbbox((0, 0), zone.name, font=font)
        legend_x += 16 + (bbox[2] - bbox[0]) + 12

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
