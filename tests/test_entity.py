"""Tests for base entity."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH

from custom_components.aiper.const import DOMAIN, MANUFACTURER
from custom_components.aiper.coordinator import IrriSenseState
from custom_components.aiper.entity import IrriSenseEntity


def _make_entity() -> IrriSenseEntity:
    coord = MagicMock()
    coord.address = "AA:BB:CC:DD:EE:FF"
    coord.config_entry.title = "My IrriSense"
    coord.data = IrriSenseState(model="IrriSense 2", firmware="3.1.0")
    entity = object.__new__(IrriSenseEntity)
    IrriSenseEntity.__init__(entity, coord)
    return entity


class TestIrriSenseEntity:
    def test_has_entity_name(self):
        entity = _make_entity()
        assert entity.has_entity_name is True

    def test_device_info_connections(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert (CONNECTION_BLUETOOTH, "AA:BB:CC:DD:EE:FF") in info["connections"]

    def test_device_info_identifiers(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert (DOMAIN, "AA:BB:CC:DD:EE:FF") in info["identifiers"]

    def test_device_info_name(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert info["name"] == "My IrriSense"

    def test_device_info_manufacturer(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert info["manufacturer"] == MANUFACTURER

    def test_device_info_model(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert info["model"] == "IrriSense 2"

    def test_device_info_firmware(self):
        entity = _make_entity()
        info = entity._attr_device_info
        assert info["sw_version"] == "3.1.0"

    def test_device_info_no_firmware(self):
        coord = MagicMock()
        coord.address = "AA:BB:CC:DD:EE:FF"
        coord.config_entry.title = "Test"
        coord.data = IrriSenseState()
        entity = object.__new__(IrriSenseEntity)
        IrriSenseEntity.__init__(entity, coord)
        assert entity._attr_device_info["sw_version"] is None
