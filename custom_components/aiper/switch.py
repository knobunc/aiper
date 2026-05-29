"""Switch platform for Aiper IrriSense."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    SENSE_TYPE_RAIN_SENSOR,
    SENSE_TYPE_WEATHER_RAIN,
    SENSE_TYPE_WEATHER_WIND,
)
from .coordinator import IrriSenseCoordinator, IrriSensePlan
from .entity import IrriSenseEntity

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known_plan_ids: set[int] = set()

    entities: list[SwitchEntity] = [
        IrriSenseSenseSwitch(
            coordinator, "rain_sensor",
            SENSE_TYPE_RAIN_SENSOR, lambda s: s.rain_sensor,
        ),
        IrriSenseSenseSwitch(
            coordinator, "weather_rain",
            SENSE_TYPE_WEATHER_RAIN, lambda s: s.weather_rain,
        ),
        IrriSenseSenseSwitch(
            coordinator, "weather_wind",
            SENSE_TYPE_WEATHER_WIND, lambda s: s.weather_wind,
        ),
        IrriSenseAllSchedulesSwitch(coordinator),
    ]

    for plan in coordinator.data.plans:
        entities.append(IrriSensePlanSwitch(coordinator, plan))
        known_plan_ids.add(plan.plan_id)

    async_add_entities(entities)

    @callback
    def _check_new_plans() -> None:
        new_entities: list[SwitchEntity] = []
        for plan in coordinator.data.plans:
            if plan.plan_id not in known_plan_ids:
                new_entities.append(IrriSensePlanSwitch(coordinator, plan))
                known_plan_ids.add(plan.plan_id)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.set_plan_update_callback(_check_new_plans)


class IrriSenseSenseSwitch(IrriSenseEntity, SwitchEntity):
    """Switch for rain sensor / weather sensor settings."""

    def __init__(
        self,
        coordinator: IrriSenseCoordinator,
        key: str,
        sense_type: int,
        value_fn,
    ) -> None:
        super().__init__(coordinator)
        self._sense_type = sense_type
        self._value_fn = value_fn
        self._attr_unique_id = f"{coordinator.address}-{key}"
        self._attr_translation_key = key

    @property
    def is_on(self) -> bool:
        return self._value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sense_switch(self._sense_type, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_sense_switch(self._sense_type, False)


class IrriSensePlanSwitch(IrriSenseEntity, SwitchEntity):
    """Switch to enable/disable an irrigation plan."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: IrriSenseCoordinator,
        plan: IrriSensePlan,
    ) -> None:
        super().__init__(coordinator)
        self._plan_id = plan.plan_id
        self._attr_unique_id = f"{coordinator.address}-plan-{plan.plan_id}"
        self._attr_name = f"Plan: {plan.name}"

    @property
    def is_on(self) -> bool | None:
        for plan in self.coordinator.data.plans:
            if plan.plan_id == self._plan_id:
                self._attr_name = f"Plan: {plan.name}"
                return plan.enabled
        return None

    @property
    def available(self) -> bool:
        return super().available and any(
            p.plan_id == self._plan_id for p in self.coordinator.data.plans
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_plan_enabled([self._plan_id], True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_plan_enabled([self._plan_id], False)


class IrriSenseAllSchedulesSwitch(IrriSenseEntity, SwitchEntity):
    """Switch to enable/disable all irrigation plans."""

    _attr_icon = "mdi:calendar-check"
    _attr_translation_key = "all_schedules"

    def __init__(self, coordinator: IrriSenseCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-all-schedules"

    @property
    def is_on(self) -> bool:
        return any(p.enabled for p in self.coordinator.data.plans)

    async def async_turn_on(self, **kwargs: Any) -> None:
        ids = [p.plan_id for p in self.coordinator.data.plans]
        if ids:
            await self.coordinator.async_set_plan_enabled(ids, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        ids = [p.plan_id for p in self.coordinator.data.plans]
        if ids:
            await self.coordinator.async_set_plan_enabled(ids, False)
