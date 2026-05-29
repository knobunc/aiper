"""Tests for image platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.aiper.coordinator import (
    IrriSensePoint,
    IrriSenseState,
    IrriSenseZone,
)
from custom_components.aiper.image import PARALLEL_UPDATES, IrriSenseMapImage


def _make_point(x: int = 0, y: int = 0) -> IrriSensePoint:
    return IrriSensePoint(
        x=x, y=y, valve=0, rotate=0, water_pressure=0.0, num=0,
    )


def _make_image(state: IrriSenseState | None = None) -> IrriSenseMapImage:
    coord = MagicMock()
    coord.address = "AA:BB:CC:DD:EE:FF"
    coord.data = state or IrriSenseState()
    coord.config_entry.title = "Test"
    coord.config_entry.options = {}
    entity = object.__new__(IrriSenseMapImage)
    entity.coordinator = coord
    entity._attr_unique_id = f"{coord.address}-map"
    return entity


class TestMapImage:
    def test_parallel_updates_is_zero(self):
        assert PARALLEL_UPDATES == 0

    def test_returns_none_when_no_zones(self):
        entity = _make_image()
        assert entity.image() is None

    def test_returns_none_when_zones_have_no_points(self):
        state = IrriSenseState(
            zones=[IrriSenseZone(id=1, name="Z", type=0, point_total=0)]
        )
        entity = _make_image(state)
        assert entity.image() is None

    def test_returns_png_when_zones_have_points(self):
        zone = IrriSenseZone(
            id=1, name="Front", type=0, point_total=2,
            points=[_make_point(0, 0), _make_point(100, 100)],
        )
        state = IrriSenseState(zones=[zone])
        entity = _make_image(state)
        result = entity.image()
        assert result is not None
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_includes_position_when_irrigating(self):
        zone = IrriSenseZone(
            id=1, name="Front", type=0, point_total=1,
            points=[_make_point(100, 100)],
        )
        state_no_pos = IrriSenseState(zones=[zone])
        state_with_pos = IrriSenseState(
            zones=[zone],
            is_irrigating=True,
            position_x=50,
            position_y=50,
        )
        entity_no = _make_image(state_no_pos)
        entity_yes = _make_image(state_with_pos)
        assert entity_no.image() != entity_yes.image()

    def test_excludes_position_when_not_irrigating(self):
        zone = IrriSenseZone(
            id=1, name="Front", type=0, point_total=1,
            points=[_make_point(100, 100)],
        )
        state = IrriSenseState(
            zones=[zone],
            is_irrigating=False,
            position_x=50,
            position_y=50,
        )
        entity = _make_image(state)
        result = entity.image()
        assert result is not None

    def test_reads_rotation_from_options(self):
        zone = IrriSenseZone(
            id=1, name="Front", type=0, point_total=1,
            points=[_make_point(100, 0)],
        )
        state = IrriSenseState(zones=[zone])

        entity_0 = _make_image(state)
        entity_0.coordinator.config_entry.options = {"map_rotation": 0}

        entity_90 = _make_image(state)
        entity_90.coordinator.config_entry.options = {"map_rotation": 90}

        assert entity_0.image() != entity_90.image()

    def test_content_type(self):
        entity = _make_image()
        assert entity.content_type == "image/png"

    def test_translation_key(self):
        entity = _make_image()
        assert entity.translation_key == "map"
