"""Aiper IrriSense integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .coordinator import IrriSenseCoordinator

_LOGGER = logging.getLogger(__name__)

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AiperConfigEntry) -> bool:
    """Set up Aiper IrriSense from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    coordinator = IrriSenseCoordinator(hass, address, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: AiperConfigEntry) -> bool:
    """Unload Aiper IrriSense config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _find_coordinator(
    hass: HomeAssistant, device_id: str
) -> IrriSenseCoordinator:
    """Resolve a device_id to its IrriSenseCoordinator."""
    dev_reg = dr.async_get(hass)
    device_entry = dev_reg.async_get(device_id)
    if device_entry is None:
        raise ServiceValidationError(f"Device {device_id} not found")

    for entry_id in device_entry.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN and hasattr(entry, "runtime_data"):
            return entry.runtime_data

    raise ServiceValidationError(f"No Aiper coordinator for device {device_id}")


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Register Aiper services."""
    if hass.services.has_service(DOMAIN, "stop"):
        return

    async def handle_start(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        map_id = call.data["map_id"]
        water_yield = call.data.get("water_yield", 0.25)
        await coordinator.async_start_irrigation(int(map_id), float(water_yield))

    async def handle_stop(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        await coordinator.async_stop_irrigation()

    async def handle_water_area(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        segment_ids = call.data["segment_ids"]
        water_yield = float(call.data.get("water_yield", 0.25))
        point_time = int(call.data.get("point_time", 1))

        if isinstance(segment_ids, str):
            segment_ids = [s.strip() for s in segment_ids.split(",")]

        for seg_id in segment_ids:
            await coordinator.async_start_irrigation(
                int(seg_id), water_yield, point_time
            )

    async def handle_turn_on(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        ids = [p.plan_id for p in coordinator.data.plans]
        if ids:
            await coordinator.async_set_plan_enabled(ids, True)

    async def handle_turn_off(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        ids = [p.plan_id for p in coordinator.data.plans]
        if ids:
            await coordinator.async_set_plan_enabled(ids, False)

    async def handle_toggle(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        any_enabled = any(p.enabled for p in coordinator.data.plans)
        ids = [p.plan_id for p in coordinator.data.plans]
        if ids:
            await coordinator.async_set_plan_enabled(ids, not any_enabled)

    async def handle_send_command(call: ServiceCall) -> None:
        coordinator = _find_coordinator(hass, call.data["device_id"])
        command = call.data["command"]
        data = call.data.get("data")
        await coordinator.async_send_raw_command(command, data)

    hass.services.async_register(DOMAIN, "start", handle_start)
    hass.services.async_register(DOMAIN, "stop", handle_stop)
    hass.services.async_register(DOMAIN, "pause", handle_stop)
    hass.services.async_register(DOMAIN, "water_area", handle_water_area)
    hass.services.async_register(DOMAIN, "turn_on", handle_turn_on)
    hass.services.async_register(DOMAIN, "turn_off", handle_turn_off)
    hass.services.async_register(DOMAIN, "toggle", handle_toggle)
    hass.services.async_register(DOMAIN, "send_command", handle_send_command)
