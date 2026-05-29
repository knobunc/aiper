"""Tests for binary sensor platform."""

from __future__ import annotations

from custom_components.aiper.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    PARALLEL_UPDATES,
)
from custom_components.aiper.coordinator import IrriSenseState


class TestBinarySensorDescriptions:
    def test_parallel_updates_is_zero(self):
        assert PARALLEL_UPDATES == 0

    def test_irrigating_true(self):
        state = IrriSenseState(is_irrigating=True)
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "irrigating")
        assert desc.value_fn(state) is True

    def test_irrigating_false(self):
        state = IrriSenseState()
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "irrigating")
        assert desc.value_fn(state) is False

    def test_rain_detected_true(self):
        state = IrriSenseState(rain_detected=True)
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "rain_detected")
        assert desc.value_fn(state) is True

    def test_rain_detected_false(self):
        state = IrriSenseState()
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "rain_detected")
        assert desc.value_fn(state) is False

    def test_water_shortage_true(self):
        state = IrriSenseState(water_shortage=True)
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "water_shortage")
        assert desc.value_fn(state) is True

    def test_water_shortage_false(self):
        state = IrriSenseState()
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "water_shortage")
        assert desc.value_fn(state) is False

    def test_connected_true(self):
        state = IrriSenseState(available=True)
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "connected")
        assert desc.value_fn(state) is True

    def test_connected_false(self):
        state = IrriSenseState()
        desc = next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == "connected")
        assert desc.value_fn(state) is False

    def test_all_descriptions_have_translation_keys(self):
        for desc in BINARY_SENSOR_DESCRIPTIONS:
            assert desc.translation_key, f"{desc.key} missing translation_key"

    def test_all_descriptions_have_device_class(self):
        for desc in BINARY_SENSOR_DESCRIPTIONS:
            assert desc.device_class, f"{desc.key} missing device_class"
