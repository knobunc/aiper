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

PARALLEL_UPDATES = 0

_WEEKDAY_ABBR = {0: "Su", 1: "M", 2: "T", 3: "W", 4: "Th", 5: "F", 6: "Sa"}


def _format_weekdays(weekdays: list[int]) -> str:
    """Format weekday list into abbreviated string like MWF or Daily."""
    if sorted(weekdays) == list(range(7)):
        return "Daily"
    return "".join(_WEEKDAY_ABBR.get(d, "?") for d in sorted(weekdays))


def _plan_display_name(plan: IrriSensePlan) -> str:
    """Build a descriptive plan name: zone + start time + weekdays + depth."""
    parts = [f"Plan: {plan.zone_name or plan.name}"]
    if plan.start_time:
        parts.append(plan.start_time)
    if plan.weekdays:
        parts.append(_format_weekdays(plan.weekdays))
    if plan.depth:
        parts.append(f"{round(plan.depth, 2)}in")
    return " ".join(parts)

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
    entry.async_on_unload(
        lambda: coordinator.set_plan_update_callback(lambda: None)
    )


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
        self._attr_name = _plan_display_name(plan)

    def _find_plan(self) -> IrriSensePlan | None:
        for plan in self.coordinator.data.plans:
            if plan.plan_id == self._plan_id:
                return plan
        return None

    @property
    def is_on(self) -> bool | None:
        plan = self._find_plan()
        if plan is None:
            return None
        self._attr_name = _plan_display_name(plan)
        return plan.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        plan = self._find_plan()
        if plan is None:
            return None
        return {
            "plan_id": plan.plan_id,
            "zone_name": plan.zone_name,
            "zone_id": plan.zone_id,
            "start_time": plan.start_time,
            "weekdays": _format_weekdays(plan.weekdays) if plan.weekdays else None,
            "weekdays_raw": plan.weekdays,
            "depth_inches": round(plan.depth, 2),
            "point_time_minutes": plan.point_time,
            "estimated_time_minutes": plan.estimated_time,
            "repeat_type": plan.repeat_type,
        }

    @property
    def available(self) -> bool:
        return super().available and self._find_plan() is not None

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
