"""DataUpdateCoordinator for Aiper IrriSense — connect-poll-disconnect cycle."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble_client import DeviceUnavailable, IrriSenseClient
from .const import (
    DOMAIN,
    POLL_IDLE,
    POLL_IRRIGATING,
    POLL_UNAVAILABLE,
    ZONE_DISCOVERY_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class IrriSensePoint:
    """A single waypoint within a zone."""

    x: int
    y: int
    valve: int
    rotate: int
    water_pressure: float
    num: int


@dataclass
class IrriSenseZone:
    """A zone/map region on the device."""

    id: int
    name: str
    type: int
    point_total: int
    points: list[IrriSensePoint] = field(default_factory=list)


@dataclass
class IrriSensePlan:
    """An irrigation plan/schedule."""

    plan_id: int
    name: str
    zone_name: str
    zone_id: int
    zone_type: int
    start_time: str
    weekdays: list[int]
    repeat_type: int
    depth: float
    point_time: int
    enabled: bool
    estimated_time: int


@dataclass
class IrriSenseState:
    """Complete device state, updated each poll cycle."""

    # DevInfo
    model: str = ""
    serial: str = ""
    firmware: str = ""

    # workInfo
    status: int = 0
    valve: int = 0
    rotate: int = 0
    water_pressure: float = 0.0

    # workInfo / realTimeProgress (during irrigation)
    current_zone: str | None = None
    current_zone_id: int | None = None
    run_time: int = 0
    progress: int = 0
    position_x: int | None = None
    position_y: int | None = None
    water_yield: float | None = None
    point_time: int | None = None
    current_plan_id: int | None = None

    # Alarm
    warn_code: int = 0

    # GetSenseSwitch
    rain_sensor: bool = True
    weather_rain: bool = True
    weather_wind: bool = True

    # Computed
    is_irrigating: bool = False
    rain_detected: bool = False
    water_shortage: bool = False

    # Location (set by phone app during install)
    latitude: float | None = None
    longitude: float | None = None

    # Connection
    rssi: int | None = None
    available: bool = False

    # Zone/plan data
    zones: list[IrriSenseZone] = field(default_factory=list)
    plans: list[IrriSensePlan] = field(default_factory=list)


class IrriSenseCoordinator(DataUpdateCoordinator[IrriSenseState]):
    """Coordinator that manages connect-poll-disconnect BLE cycles."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{address}",
            update_interval=timedelta(seconds=POLL_IDLE),
        )
        self._address = address
        self._client = IrriSenseClient(hass, address)
        self._state = IrriSenseState()
        self.data = self._state
        self._last_zone_discovery: float = 0
        self._plan_update_callback: Callable[[], None] | None = None
        self._was_available: bool = False
        self._consecutive_failures: int = 0

    @property
    def address(self) -> str:
        return self._address

    def set_plan_update_callback(self, callback: Callable[[], None]) -> None:
        self._plan_update_callback = callback

    async def _async_update_data(self) -> IrriSenseState:
        client = self._client
        try:
            await client.connect()
        except (BleakError, TimeoutError, DeviceUnavailable) as err:
            self._consecutive_failures += 1
            self._state.available = False
            if self._was_available:
                _LOGGER.warning(
                    "Device %s is unavailable: %s", self._address, err
                )
                self._was_available = False
            else:
                _LOGGER.debug("BLE connect failed, will retry: %s", err)
            self.update_interval = timedelta(seconds=POLL_UNAVAILABLE)
            raise UpdateFailed(f"Device unavailable: {err}") from err

        try:
            self._consecutive_failures = 0
            self._state.rssi = client.rssi
            self._state.available = True
            if not self._was_available:
                _LOGGER.info("Device %s is available", self._address)
                self._was_available = True

            # Drain any unsolicited notifications that arrived during
            # connect (the device proactively sends Alarm on connect).
            for notif in client.drain_unsolicited():
                self._process_unsolicited(notif)

            work = await client.send_command("workInfo")
            if work and work.get("res") != -1:
                self._apply_work_info(work["data"])

            if not self._state.is_irrigating:
                dev = await client.send_command("DevInfo")
                if dev and dev.get("res") != -1:
                    self._apply_dev_info(dev["data"])

                sense = await client.send_command("GetSenseSwitch")
                if sense and sense.get("res") != -1:
                    self._apply_sense_switch(sense["data"])

            now = time.monotonic()
            if (
                not self._state.is_irrigating
                and now - self._last_zone_discovery > ZONE_DISCOVERY_INTERVAL
            ):
                await self._discover_zones_and_plans(client)
                await self._fetch_location(client)
                self._last_zone_discovery = now

            # Drain any unsolicited notifications that arrived during
            # the poll cycle.
            for notif in client.drain_unsolicited():
                self._process_unsolicited(notif)

            if self._state.is_irrigating:
                self.update_interval = timedelta(seconds=POLL_IRRIGATING)
            else:
                self.update_interval = timedelta(seconds=POLL_IDLE)

            return self._state

        except (BleakError, TimeoutError) as err:
            raise UpdateFailed(f"BLE poll failed: {err}") from err
        finally:
            await client.disconnect()

    def _apply_work_info(self, data: dict[str, Any]) -> None:
        self._state.status = data.get("status", 0)
        self._state.valve = data.get("valve", 0)
        self._state.rotate = data.get("rotate", 0)
        self._state.water_pressure = data.get("waterpress", 0.0)
        self._state.is_irrigating = self._state.status == 1

        if not self._state.is_irrigating:
            self._state.current_zone = None
            self._state.current_zone_id = None
            self._state.run_time = 0
            self._state.progress = 0
            self._state.position_x = None
            self._state.position_y = None
            self._state.water_yield = None
            self._state.point_time = None
            self._state.current_plan_id = None

    def _apply_dev_info(self, data: dict[str, Any]) -> None:
        self._state.model = data.get("model", self._state.model)
        self._state.serial = data.get("sn", self._state.serial)
        self._state.firmware = data.get("version", self._state.firmware)

    def _apply_alarm(self, data: dict[str, Any]) -> None:
        if "warnCode" in data:
            warn_code = data["warnCode"]
            self._state.warn_code = warn_code
            self._state.rain_detected = bool(warn_code & 0x04)
            self._state.water_shortage = bool(warn_code & 0x02)
        elif "code" in data:
            codes = data["code"]
            self._state.rain_detected = 4 in codes
            self._state.water_shortage = 2 in codes
            self._state.warn_code = sum(codes) if codes else 0

    def _apply_sense_switch(self, data: dict[str, Any]) -> None:
        self._state.rain_sensor = bool(data.get("rainSensing", 1))
        self._state.weather_rain = bool(data.get("weatherRain", 1))
        self._state.weather_wind = bool(data.get("weatherWind", 1))

    async def _discover_zones_and_plans(self, client: IrriSenseClient) -> None:
        overview = await client.send_command("WrMapManageOverView")
        _LOGGER.debug("WrMapManageOverView: %s", overview)
        if overview and overview.get("data"):
            map_list = overview["data"]
            if isinstance(map_list, dict):
                map_list = map_list.get("map_list", [])
            self._state.zones = [
                IrriSenseZone(
                    id=m.get("id", 0),
                    name=m.get("name", ""),
                    type=m.get("type", 0),
                    point_total=m.get("point_total", m.get("count", 0)),
                )
                for m in map_list
            ]

        await self._fetch_zone_points(client)

        plan_overview = await client.send_command("WrPlanOverview")
        _LOGGER.debug("WrPlanOverview: %s", plan_overview)
        if not plan_overview or not plan_overview.get("data"):
            return

        used_ids = plan_overview["data"].get("used_ids", [])
        old_plan_ids = {p.plan_id for p in self._state.plans}
        plans: list[IrriSensePlan] = []

        for plan_id in used_ids:
            detail = await client.send_command(
                "WrPlanDetail", {"plan_id": plan_id}
            )
            _LOGGER.debug("WrPlanDetail %d: %s", plan_id, detail)
            if not detail or not detail.get("data"):
                continue
            d = detail["data"]
            mi = d.get("map_info", {})
            wc = d.get("work_ctrl", {})
            tc = d.get("time_ctrl", {})
            plans.append(
                IrriSensePlan(
                    plan_id=d.get("plan_id", plan_id),
                    name=mi.get("name", f"Plan {plan_id}"),
                    zone_name=mi.get("name", ""),
                    zone_id=mi.get("id", 0),
                    zone_type=mi.get("type", 0),
                    start_time=tc.get("start_time", ""),
                    weekdays=tc.get("weekdays", []),
                    repeat_type=tc.get("repeat_type", 0),
                    depth=wc.get("depth", 0.0),
                    point_time=wc.get("point_time", 1),
                    enabled=d.get("enabled", False),
                    estimated_time=d.get("estimated_time", 0),
                )
            )

        self._state.plans = plans
        _LOGGER.debug(
            "Discovered %d plans: %s",
            len(plans),
            [
                (p.plan_id, p.name, p.enabled, p.start_time, p.weekdays)
                for p in plans
            ],
        )

        new_plan_ids = {p.plan_id for p in plans}
        if new_plan_ids != old_plan_ids and self._plan_update_callback:
            self._plan_update_callback()

    async def _fetch_zone_points(self, client: IrriSenseClient) -> None:
        """Fetch individual waypoints for each zone."""
        for zone in self._state.zones:
            points: list[IrriSensePoint] = []
            for i in range(zone.point_total):
                resp = await client.send_command(
                    "WrMapManageSingleInfo",
                    {"id": zone.id, "type": zone.type, "point_index": i},
                )
                if resp and resp.get("data"):
                    pt = resp["data"].get("point_info", {})
                    points.append(
                        IrriSensePoint(
                            x=pt.get("x", 0),
                            y=pt.get("y", 0),
                            valve=pt.get("valve", 0),
                            rotate=pt.get("rotate", 0),
                            water_pressure=pt.get("waterpress", 0.0),
                            num=pt.get("num", i),
                        )
                    )
            zone.points = points
        _LOGGER.debug(
            "Fetched points for %d zones: %s",
            len(self._state.zones),
            [(z.name, len(z.points)) for z in self._state.zones],
        )

    async def _fetch_location(self, client: IrriSenseClient) -> None:
        loc = await client.send_command("locationGet")
        _LOGGER.debug("locationGet: %s", loc)
        if loc and loc.get("data"):
            d = loc["data"]
            self._state.latitude = d.get("latitude")
            self._state.longitude = d.get("longitude")

    def _process_unsolicited(self, notif: dict[str, Any]) -> None:
        ntype = notif.get("type")
        data = notif.get("data", {})

        if ntype == "realTimeProgress":
            self._state.is_irrigating = data.get("status", 0) == 1
            self._state.run_time = data.get("time", 0)
            self._state.progress = data.get("progress", 0)
            self._state.position_x = data.get("x")
            self._state.position_y = data.get("y")
            self._state.water_yield = data.get("waterYield")
            self._state.point_time = data.get("point_time")
            self._state.current_plan_id = data.get("plan_id")
            map_info = data.get("map_info", {})
            if map_info:
                self._state.current_zone = map_info.get("name")
                self._state.current_zone_id = map_info.get("id")

        elif ntype == "AbnormalReminder":
            rain = data.get("rain", {})
            if rain.get("status"):
                self._state.rain_detected = True
            hydro = data.get("hydropenia", {})
            if hydro.get("status"):
                self._state.water_shortage = True

        elif ntype == "Alarm":
            self._apply_alarm(data)

    async def _send_single_command(
        self, cmd: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Connect, send one command, disconnect, then trigger refresh."""
        try:
            await self._client.connect()
            result = await self._client.send_command(cmd, data)
            return result
        except (BleakError, TimeoutError, DeviceUnavailable) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_command_failed",
                translation_placeholders={
                    "command": cmd,
                    "address": self._address,
                },
            ) from err
        finally:
            await self._client.disconnect()

    async def async_set_sense_switch(self, sense_type: int, status: bool) -> None:
        await self._send_single_command(
            "SetSenseSwitch", {"type": sense_type, "status": int(status)}
        )
        await self.async_request_refresh()

    async def async_set_plan_enabled(
        self, plan_ids: list[int], enabled: bool
    ) -> None:
        key = "enable_plans" if enabled else "disable_plans"
        await self._send_single_command("WrPlanBatchEdit", {key: plan_ids})
        await self.async_request_refresh()

    async def async_start_irrigation(
        self,
        map_id: int,
        water_yield: float = 0.25,
        point_time: int = 1,
    ) -> None:
        await self._send_single_command(
            "setWorkMode",
            {"map_id": map_id, "status": 1, "mode": 0, "waterYield": water_yield},
        )
        await self.async_request_refresh()

    async def async_stop_irrigation(self) -> None:
        await self._send_single_command(
            "setWorkMode", {"mode": 0, "status": 0}
        )
        await self.async_request_refresh()

    async def async_send_raw_command(
        self, command: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        result = await self._send_single_command(command, data)
        await self.async_request_refresh()
        return result
