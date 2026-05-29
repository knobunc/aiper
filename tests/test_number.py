"""Tests for number platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.aiper.number import (
    CONF_MAP_ROTATION,
    PARALLEL_UPDATES,
    IrriSenseMapRotation,
)


def _make_number(options: dict | None = None) -> IrriSenseMapRotation:
    coord = MagicMock()
    coord.address = "AA:BB:CC:DD:EE:FF"
    coord.data.model = "IrriSense 2"
    coord.data.firmware = "1.0"
    coord.config_entry.title = "Test"
    coord.config_entry.options = options or {}
    entity = object.__new__(IrriSenseMapRotation)
    entity.coordinator = coord
    entity._attr_unique_id = f"{coord.address}-map-rotation"
    return entity


class TestMapRotation:
    def test_parallel_updates_is_zero(self):
        assert PARALLEL_UPDATES == 0

    def test_default_value_is_zero(self):
        entity = _make_number()
        assert entity.native_value == 0.0

    def test_reads_value_from_options(self):
        entity = _make_number({CONF_MAP_ROTATION: 180})
        assert entity.native_value == 180.0

    def test_min_value(self):
        entity = _make_number()
        assert entity.native_min_value == 0

    def test_max_value(self):
        entity = _make_number()
        assert entity.native_max_value == 359

    def test_step(self):
        entity = _make_number()
        assert entity.native_step == 1

    def test_unit(self):
        entity = _make_number()
        assert entity.native_unit_of_measurement == "°"

    def test_translation_key(self):
        entity = _make_number()
        assert entity.translation_key == "map_rotation"

    @pytest.mark.asyncio
    async def test_set_value_updates_options(self):
        entity = _make_number({CONF_MAP_ROTATION: 0})
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()

        await entity.async_set_native_value(90.0)

        entity.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = (
            entity.hass.config_entries.async_update_entry.call_args
        )
        new_opts = call_kwargs[1]["options"]
        assert new_opts[CONF_MAP_ROTATION] == 90
        entity.async_write_ha_state.assert_called_once()
