"""Base entity for Aiper IrriSense integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import IrriSenseCoordinator


class IrriSenseEntity(CoordinatorEntity[IrriSenseCoordinator]):
    """Base entity for IrriSense devices."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IrriSenseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            identifiers={(DOMAIN, coordinator.address)},
            name=coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=coordinator.data.model or "IrriSense 2",
            sw_version=coordinator.data.firmware or None,
        )
