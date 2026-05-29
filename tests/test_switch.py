"""Tests for plan switch naming and attributes."""

from custom_components.aiper.coordinator import IrriSensePlan
from custom_components.aiper.switch import _format_weekdays, _plan_display_name


def _make_plan(**overrides) -> IrriSensePlan:
    defaults = dict(
        plan_id=1,
        name="North Side",
        zone_name="North Side",
        zone_id=10,
        zone_type=0,
        start_time="07:30",
        weekdays=[1, 3, 5],
        repeat_type=0,
        depth=0.25,
        point_time=1,
        enabled=True,
        estimated_time=30,
    )
    defaults.update(overrides)
    return IrriSensePlan(**defaults)


class TestFormatWeekdays:
    def test_mwf(self):
        assert _format_weekdays([1, 3, 5]) == "MWF"

    def test_daily(self):
        assert _format_weekdays([1, 2, 3, 4, 5, 6, 7]) == "Daily"

    def test_weekend(self):
        assert _format_weekdays([6, 7]) == "SaSu"

    def test_single_day(self):
        assert _format_weekdays([2]) == "T"

    def test_unsorted_input(self):
        assert _format_weekdays([5, 1, 3]) == "MWF"

    def test_thursday(self):
        assert _format_weekdays([4]) == "Th"

    def test_tth(self):
        assert _format_weekdays([2, 4]) == "TTh"


class TestPlanDisplayName:
    def test_full_name(self):
        plan = _make_plan()
        assert _plan_display_name(plan) == "Plan: North Side 07:30 MWF 0.25in"

    def test_daily_schedule(self):
        plan = _make_plan(weekdays=[1, 2, 3, 4, 5, 6, 7])
        assert _plan_display_name(plan) == "Plan: North Side 07:30 Daily 0.25in"

    def test_no_start_time(self):
        plan = _make_plan(start_time="")
        assert _plan_display_name(plan) == "Plan: North Side MWF 0.25in"

    def test_no_weekdays(self):
        plan = _make_plan(weekdays=[])
        assert _plan_display_name(plan) == "Plan: North Side 07:30 0.25in"

    def test_no_depth(self):
        plan = _make_plan(depth=0.0)
        assert _plan_display_name(plan) == "Plan: North Side 07:30 MWF"

    def test_falls_back_to_name_if_no_zone_name(self):
        plan = _make_plan(zone_name="", name="My Plan")
        assert _plan_display_name(plan) == "Plan: My Plan 07:30 MWF 0.25in"

    def test_two_plans_same_zone_different_schedules(self):
        plan_a = _make_plan(start_time="07:30", weekdays=[1, 3, 5], depth=0.25)
        plan_b = _make_plan(
            start_time="18:00", weekdays=[1, 2, 3, 4, 5, 6, 7], depth=0.5
        )
        name_a = _plan_display_name(plan_a)
        name_b = _plan_display_name(plan_b)
        assert name_a != name_b
        assert "07:30" in name_a
        assert "18:00" in name_b
