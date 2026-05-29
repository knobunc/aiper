"""Tests for the diagnostics platform."""

from unittest.mock import MagicMock

from custom_components.aiper.coordinator import IrriSenseState
from custom_components.aiper.diagnostics import async_get_config_entry_diagnostics


class TestDiagnostics:
    async def test_returns_coordinator_state(self):
        state = IrriSenseState(model="WR200", serial="SN123", firmware="1.0")
        coordinator = MagicMock()
        coordinator.data = state
        entry = MagicMock()
        entry.runtime_data = coordinator
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert isinstance(result, dict)
        assert result["model"] == "WR200"
        assert result["serial"] == "SN123"
        assert result["firmware"] == "1.0"

    async def test_redacts_location(self):
        state = IrriSenseState(latitude=42.123456, longitude=-71.654321)
        coordinator = MagicMock()
        coordinator.data = state
        entry = MagicMock()
        entry.runtime_data = coordinator
        hass = MagicMock()

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["latitude"] == "**REDACTED**"
        assert result["longitude"] == "**REDACTED**"
