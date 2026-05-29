"""Tests for the zone map renderer."""

from __future__ import annotations

from custom_components.aiper.coordinator import IrriSensePoint, IrriSenseZone
from custom_components.aiper.map_render import _rotate, render_map


def _zone(
    name: str, points: list[tuple[int, int]], zone_id: int = 1
) -> IrriSenseZone:
    return IrriSenseZone(
        id=zone_id,
        name=name,
        type=0,
        point_total=len(points),
        points=[
            IrriSensePoint(
                x=x, y=y, valve=0, rotate=0, water_pressure=0.0, num=i
            )
            for i, (x, y) in enumerate(points)
        ],
    )


class TestRotate:
    def test_zero_rotation(self):
        assert _rotate(100, 200, 0) == (100.0, 200.0)

    def test_90_degrees(self):
        rx, ry = _rotate(100, 0, 90)
        assert abs(rx) < 1e-10
        assert abs(ry - 100) < 1e-10

    def test_180_degrees(self):
        rx, ry = _rotate(100, 50, 180)
        assert abs(rx - (-100)) < 1e-10
        assert abs(ry - (-50)) < 1e-10

    def test_360_is_identity(self):
        rx, ry = _rotate(42, 99, 360)
        assert abs(rx - 42) < 1e-10
        assert abs(ry - 99) < 1e-10


class TestRenderMap:
    def test_empty_zones_returns_valid_png(self):
        result = render_map([])
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_zones_without_points_returns_valid_png(self):
        zone = IrriSenseZone(
            id=1, name="Empty", type=0, point_total=0, points=[]
        )
        result = render_map([zone])
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_single_zone_with_points(self):
        zone = _zone("Front Lawn", [(0, 0), (100, 0), (100, 100)])
        result = render_map([zone])
        assert result[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(result) > 100

    def test_rotation_changes_output(self):
        zone = _zone("Test", [(100, 0), (0, 100)])
        img_0 = render_map([zone], rotation_degrees=0.0)
        img_90 = render_map([zone], rotation_degrees=90.0)
        assert img_0 != img_90

    def test_position_marker(self):
        zone = _zone("Test", [(0, 0), (200, 200)])
        img_no_pos = render_map([zone])
        img_with_pos = render_map([zone], position=(100, 100))
        assert img_no_pos != img_with_pos

    def test_multiple_zones_different_colors(self):
        zones = [
            _zone("Zone A", [(0, 0), (100, 0)], zone_id=1),
            _zone("Zone B", [(0, 100), (100, 100)], zone_id=2),
        ]
        result = render_map(zones)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_custom_image_size(self):
        zone = _zone("Test", [(0, 0), (100, 100)])
        result = render_map([zone], image_size=400)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_single_point_zone(self):
        zone = _zone("Solo", [(50, 50)])
        result = render_map([zone])
        assert result[:8] == b"\x89PNG\r\n\x1a\n"
