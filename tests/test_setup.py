"""Tests for integration setup and unload."""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.aiper import async_setup_entry, async_unload_entry
from custom_components.aiper.const import CONF_ADDRESS, PLATFORMS


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
    entry.runtime_data = None
    return entry


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services = MagicMock()
    hass.services.has_service.return_value = True
    return hass


class TestSetupEntry:
    async def test_creates_coordinator_and_forwards_platforms(self):
        hass = _make_hass()
        entry = _make_entry()

        with patch(
            "custom_components.aiper.IrriSenseCoordinator"
        ) as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.data = MagicMock()
            mock_coord_cls.return_value = mock_coord

            result = await async_setup_entry(hass, entry)

        assert result is True
        mock_coord.async_config_entry_first_refresh.assert_called_once()
        hass.config_entries.async_forward_entry_setups.assert_called_once_with(
            entry, PLATFORMS
        )
        assert entry.runtime_data is mock_coord


class TestUnloadEntry:
    async def test_unloads_platforms(self):
        hass = _make_hass()
        entry = _make_entry()

        result = await async_unload_entry(hass, entry)

        assert result is True
        hass.config_entries.async_unload_platforms.assert_called_once_with(
            entry, PLATFORMS
        )
