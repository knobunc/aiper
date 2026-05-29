"""Number platform for Aiper IrriSense."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IrriSenseCoordinator
from .entity import IrriSenseEntity

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]

PARALLEL_UPDATES = 0

CONF_MAP_ROTATION = "map_rotation"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([IrriSenseMapRotation(coordinator)])


class IrriSenseMapRotation(IrriSenseEntity, NumberEntity):
    """Number entity for setting the map rotation angle."""

    _attr_translation_key = "map_rotation"
    _attr_native_min_value = 0
    _attr_native_max_value = 359
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "°"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: IrriSenseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-map-rotation"

    @property
    def native_value(self) -> float:
        return float(
            self.coordinator.config_entry.options.get(CONF_MAP_ROTATION, 0)
        )

    async def async_set_native_value(self, value: float) -> None:
        new_options = dict(self.coordinator.config_entry.options)
        new_options[CONF_MAP_ROTATION] = int(value)
        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry, options=new_options
        )
        self.async_write_ha_state()
