"""Sensor platform for Aiper IrriSense."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfPressure,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import IrriSenseCoordinator, IrriSenseState
from .entity import IrriSenseEntity

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]

PARALLEL_UPDATES = 0

WEEKDAY_MAP = {0: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}


def _compute_next_run(state: IrriSenseState) -> datetime | None:
    """Compute the next scheduled run time from enabled plans."""
    now = dt_util.now()
    nearest: datetime | None = None

    for plan in state.plans:
        if not plan.enabled or not plan.weekdays or not plan.start_time:
            continue
        try:
            parts = plan.start_time.split(":")
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue

        py_weekdays = sorted(WEEKDAY_MAP.get(d, d) for d in plan.weekdays)

        for days_ahead in range(8):
            candidate = now + timedelta(days=days_ahead)
            if candidate.weekday() in py_weekdays:
                run_time = candidate.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if run_time > now:
                    if nearest is None or run_time < nearest:
                        nearest = run_time
                    break

    return nearest


@dataclass(frozen=True, kw_only=True)
class IrriSenseSensorDescription(SensorEntityDescription):
    """Sensor description with a value extraction function."""

    value_fn: Callable[[IrriSenseState], StateType | datetime]


SENSOR_DESCRIPTIONS: tuple[IrriSenseSensorDescription, ...] = (
    IrriSenseSensorDescription(
        key="status",
        translation_key="status",
        value_fn=lambda s: {0: "Idle", 1: "Irrigating"}.get(s.status, "Unknown"),
    ),
    IrriSenseSensorDescription(
        key="current_zone",
        translation_key="current_zone",
        value_fn=lambda s: s.current_zone if s.is_irrigating else "Idle",
    ),
    IrriSenseSensorDescription(
        key="run_time",
        translation_key="run_time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.run_time if s.is_irrigating else 0,
    ),
    IrriSenseSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.progress if s.is_irrigating else 0,
    ),
    IrriSenseSensorDescription(
        key="water_pressure",
        translation_key="water_pressure",
        native_unit_of_measurement=UnitOfPressure.PSI,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: round(s.water_pressure, 1),
    ),
    IrriSenseSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.firmware or None,
    ),
    IrriSenseSensorDescription(
        key="next_run",
        translation_key="next_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: _compute_next_run(s),
    ),
    IrriSenseSensorDescription(
        key="valve",
        translation_key="valve",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.valve,
    ),
    IrriSenseSensorDescription(
        key="model",
        translation_key="model",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.model or None,
    ),
    IrriSenseSensorDescription(
        key="serial",
        translation_key="serial",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.serial or None,
    ),
    IrriSenseSensorDescription(
        key="latitude",
        translation_key="latitude",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: round(s.latitude, 6) if s.latitude else None,
    ),
    IrriSenseSensorDescription(
        key="longitude",
        translation_key="longitude",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: round(s.longitude, 6) if s.longitude else None,
    ),
    IrriSenseSensorDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        IrriSenseSensor(coordinator, desc) for desc in SENSOR_DESCRIPTIONS
    )


class IrriSenseSensor(IrriSenseEntity, SensorEntity):
    """Sensor entity for IrriSense."""

    entity_description: IrriSenseSensorDescription

    def __init__(
        self,
        coordinator: IrriSenseCoordinator,
        description: IrriSenseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}-{description.key}"

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)
