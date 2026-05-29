"""Diagnostics support for Aiper IrriSense."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import IrriSenseCoordinator

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]

TO_REDACT = {"latitude", "longitude"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AiperConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: IrriSenseCoordinator = entry.runtime_data
    data = asdict(coordinator.data)
    for key in TO_REDACT:
        if key in data:
            data[key] = "**REDACTED**"
    return data
