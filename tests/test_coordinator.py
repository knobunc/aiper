"""Tests for coordinator state parsing and data models."""

from custom_components.aiper.coordinator import (
    IrriSenseCoordinator,
    IrriSensePlan,
    IrriSenseState,
    IrriSenseZone,
)


def _make_coordinator() -> IrriSenseCoordinator:
    """Create a coordinator with mocked HA dependencies."""
    coord = object.__new__(IrriSenseCoordinator)
    coord._state = IrriSenseState()
    coord._was_available = False
    coord._consecutive_failures = 0
    return coord


class TestIrriSenseState:
    def test_defaults(self):
        state = IrriSenseState()
        assert state.model == ""
        assert state.serial == ""
        assert state.status == 0
        assert state.is_irrigating is False
        assert state.rain_detected is False
        assert state.water_shortage is False
        assert state.available is False
        assert state.zones == []
        assert state.plans == []

    def test_zone_construction(self):
        zone = IrriSenseZone(id=1, name="Front", type=2, point_total=10)
        assert zone.id == 1
        assert zone.name == "Front"

    def test_plan_construction(self):
        plan = IrriSensePlan(
            plan_id=1, name="Morning", zone_name="Front", zone_id=1,
            zone_type=2, start_time="06:00", weekdays=[1, 3, 5],
            repeat_type=0, depth=0.25, point_time=1, enabled=True,
            estimated_time=30,
        )
        assert plan.plan_id == 1
        assert plan.enabled is True


class TestApplyWorkInfo:
    def test_idle(self):
        coord = _make_coordinator()
        data = {"status": 0, "valve": 1, "rotate": 0, "waterpress": 2.5}
        coord._apply_work_info(data)
        assert coord._state.is_irrigating is False
        assert coord._state.valve == 1
        assert coord._state.water_pressure == 2.5
        assert coord._state.current_zone is None
        assert coord._state.run_time == 0
        assert coord._state.position_x is None
        assert coord._state.position_y is None
        assert coord._state.water_yield is None
        assert coord._state.point_time is None
        assert coord._state.current_plan_id is None

    def test_irrigating(self):
        coord = _make_coordinator()
        data = {"status": 1, "valve": 1, "rotate": 1, "waterpress": 3.0}
        coord._apply_work_info(data)
        assert coord._state.is_irrigating is True

    def test_missing_fields_use_defaults(self):
        coord = _make_coordinator()
        coord._apply_work_info({})
        assert coord._state.status == 0
        assert coord._state.valve == 0
        assert coord._state.water_pressure == 0.0


class TestApplyDevInfo:
    def test_extracts_fields(self):
        coord = _make_coordinator()
        coord._apply_dev_info({"model": "WR200", "sn": "SN123", "version": "1.2.3"})
        assert coord._state.model == "WR200"
        assert coord._state.serial == "SN123"
        assert coord._state.firmware == "1.2.3"

    def test_preserves_existing_on_missing(self):
        coord = _make_coordinator()
        coord._state.model = "OldModel"
        coord._apply_dev_info({})
        assert coord._state.model == "OldModel"


class TestApplyAlarm:
    """Test both warnCode (legacy) and code-list (current device) formats."""

    def test_warn_code_rain_only(self):
        coord = _make_coordinator()
        coord._apply_alarm({"warnCode": 0x04})
        assert coord._state.rain_detected is True
        assert coord._state.water_shortage is False

    def test_warn_code_water_shortage_only(self):
        coord = _make_coordinator()
        coord._apply_alarm({"warnCode": 0x02})
        assert coord._state.rain_detected is False
        assert coord._state.water_shortage is True

    def test_warn_code_both_alarms(self):
        coord = _make_coordinator()
        coord._apply_alarm({"warnCode": 0x06})
        assert coord._state.rain_detected is True
        assert coord._state.water_shortage is True

    def test_warn_code_clear(self):
        coord = _make_coordinator()
        coord._state.rain_detected = True
        coord._state.water_shortage = True
        coord._apply_alarm({"warnCode": 0})
        assert coord._state.rain_detected is False
        assert coord._state.water_shortage is False

    def test_code_list_empty(self):
        coord = _make_coordinator()
        coord._state.rain_detected = True
        coord._apply_alarm({"code": [], "timestamp": 1780027614000})
        assert coord._state.rain_detected is False
        assert coord._state.water_shortage is False
        assert coord._state.warn_code == 0

    def test_code_list_rain(self):
        coord = _make_coordinator()
        coord._apply_alarm({"code": [4], "timestamp": 1780027614000})
        assert coord._state.rain_detected is True
        assert coord._state.water_shortage is False

    def test_code_list_water(self):
        coord = _make_coordinator()
        coord._apply_alarm({"code": [2], "timestamp": 1780027614000})
        assert coord._state.rain_detected is False
        assert coord._state.water_shortage is True

    def test_code_list_both(self):
        coord = _make_coordinator()
        coord._apply_alarm({"code": [2, 4], "timestamp": 1780027614000})
        assert coord._state.rain_detected is True
        assert coord._state.water_shortage is True


class TestApplySenseSwitch:
    def test_all_enabled(self):
        coord = _make_coordinator()
        data = {"rainSensing": 1, "weatherRain": 1, "weatherWind": 1}
        coord._apply_sense_switch(data)
        assert coord._state.rain_sensor is True
        assert coord._state.weather_rain is True
        assert coord._state.weather_wind is True

    def test_all_disabled(self):
        coord = _make_coordinator()
        data = {"rainSensing": 0, "weatherRain": 0, "weatherWind": 0}
        coord._apply_sense_switch(data)
        assert coord._state.rain_sensor is False
        assert coord._state.weather_rain is False
        assert coord._state.weather_wind is False


class TestProcessUnsolicited:
    def test_realtime_progress(self):
        coord = _make_coordinator()
        coord._process_unsolicited({
            "type": "realTimeProgress",
            "data": {
                "status": 1,
                "time": 120,
                "progress": 45,
                "map_info": {"name": "Back Yard", "id": 3},
                "x": -288,
                "y": 1123,
                "waterYield": 0.25,
                "point_time": 99,
                "plan_id": 2,
            },
        })
        assert coord._state.is_irrigating is True
        assert coord._state.run_time == 120
        assert coord._state.progress == 45
        assert coord._state.current_zone == "Back Yard"
        assert coord._state.current_zone_id == 3
        assert coord._state.position_x == -288
        assert coord._state.position_y == 1123
        assert coord._state.water_yield == 0.25
        assert coord._state.point_time == 99
        assert coord._state.current_plan_id == 2

    def test_abnormal_reminder_rain(self):
        coord = _make_coordinator()
        coord._process_unsolicited({
            "type": "AbnormalReminder",
            "data": {"rain": {"status": 1}, "hydropenia": {"status": 0}},
        })
        assert coord._state.rain_detected is True
        assert coord._state.water_shortage is False

    def test_abnormal_reminder_water_shortage(self):
        coord = _make_coordinator()
        coord._process_unsolicited({
            "type": "AbnormalReminder",
            "data": {"rain": {"status": 0}, "hydropenia": {"status": 1}},
        })
        assert coord._state.water_shortage is True

    def test_alarm_unsolicited_warn_code(self):
        coord = _make_coordinator()
        coord._process_unsolicited({
            "type": "Alarm",
            "data": {"warnCode": 0x04},
        })
        assert coord._state.rain_detected is True

    def test_alarm_unsolicited_code_list(self):
        coord = _make_coordinator()
        coord._process_unsolicited({
            "type": "Alarm",
            "data": {"code": [], "timestamp": 1780027614000},
        })
        assert coord._state.rain_detected is False
        assert coord._state.water_shortage is False


class TestAvailabilityTracking:
    def test_initial_state(self):
        coord = _make_coordinator()
        assert coord._was_available is False
        assert coord._consecutive_failures == 0

    def test_consecutive_failures_tracked(self):
        coord = _make_coordinator()
        coord._consecutive_failures = 5
        assert coord._consecutive_failures == 5
