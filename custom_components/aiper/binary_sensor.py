"""Binary sensor platform for Aiper IrriSense."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IrriSenseCoordinator, IrriSenseState
from .entity import IrriSenseEntity

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class IrriSenseBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value extraction function."""

    value_fn: Callable[[IrriSenseState], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[IrriSenseBinarySensorDescription, ...] = (
    IrriSenseBinarySensorDescription(
        key="irrigating",
        translation_key="irrigating",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.is_irrigating,
    ),
    IrriSenseBinarySensorDescription(
        key="rain_detected",
        translation_key="rain_detected",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda s: s.rain_detected,
    ),
    IrriSenseBinarySensorDescription(
        key="water_shortage",
        translation_key="water_shortage",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.water_shortage,
    ),
    IrriSenseBinarySensorDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.available,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        IrriSenseBinarySensor(coordinator, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class IrriSenseBinarySensor(IrriSenseEntity, BinarySensorEntity):
    """Binary sensor entity for IrriSense."""

    entity_description: IrriSenseBinarySensorDescription

    def __init__(
        self,
        coordinator: IrriSenseCoordinator,
        description: IrriSenseBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}-{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)
