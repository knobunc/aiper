# Home Assistant Integration Proposal: Aiper IrriSense 2

**Date:** 2026-05-28
**Device:** IrriSense 2 (WR device type) — smart irrigation controller
**Transport:** BLE via HA Bluetooth integration (local adapters + ESPHome proxies)
**Protocol reference:** `AIPER_IRRISENSE2_BLE_SPEC.md`

---

## 1. Architecture

### Connection Strategy: Connect-Poll-Disconnect

The integration uses a **connect-poll-disconnect** cycle rather than a persistent BLE connection. This avoids blocking the Aiper phone app (the device only accepts one BLE connection at a time).

```
┌─────────────────────────────────────────────────┐
│  HA Bluetooth Integration                       │
│                                                 │
│  ┌─────────────┐     ┌──────────────────────┐   │
│  │ Config Flow  │────>│ IrriSenseCoordinator │   │
│  │ (discovery)  │     │ (DataUpdateCoord.)   │   │
│  └─────────────┘     └──────────┬───────────┘   │
│                                 │               │
│              ┌──────────────────┼───────┐       │
│              │  Poll cycle      │       │       │
│              │                  v       │       │
│              │  1. BLE connect          │       │
│              │  2. Send commands        │       │
│              │  3. Collect responses    │       │
│              │  4. BLE disconnect       │       │
│              │  5. Update entities      │       │
│              └──────────────────────────┘       │
└─────────────────────────────────────────────────┘
         │                              │
         v                              v
    Local BLE adapter            ESPHome BLE proxy
         │                              │
         └──────────BLE─────────────────┘
                    │
                    v
            IrriSense 2 device
```

### Adaptive Polling Intervals

| Device State | Poll Interval | Commands per Cycle |
|-------------|---------------|-------------------|
| Idle | 60 seconds | DevInfo, workInfo, Alarm, GetSenseSwitch |
| Irrigating | 15 seconds | workInfo, Alarm |
| Unavailable | 120 seconds (backoff) | DevInfo (reconnect probe) |

State transitions:
- **Idle → Irrigating:** `workInfo` returns `status: 1`
- **Irrigating → Idle:** `workInfo` returns `status: 0`
- **Any → Unavailable:** BLE connection fails (device out of range or powered off)
- **Unavailable → Idle:** BLE connection succeeds again

### Poll Cycle Detail

Each poll cycle is a single BLE session:

1. Connect to device (BleakClient via HA bluetooth)
2. Subscribe to NUS TX notifications
3. Send each command sequentially, waiting for response
4. Separate unsolicited notifications (realTimeProgress, AbnormalReminder) from command responses
5. Disconnect
6. Update all entity states from collected responses

Commands are sent sequentially within a cycle because the device processes one command at a time and responses must be matched by type.

### Protocol Layer

Reusable module for future pool robot support:

```
custom_components/aiper/
├── __init__.py
├── manifest.json
├── config_flow.py
├── coordinator.py          # DataUpdateCoordinator subclass
├── const.py                # UUIDs, XOR key, command names
├── protocol.py             # xor_crypt, build_command, parse_response
├── ble_client.py           # BLE connect/send/receive/disconnect
├── sensor.py
├── binary_sensor.py
├── switch.py
├── button.py
├── number.py
└── strings.json
```

---

## 2. Entity Catalog

### Sensors

| Entity ID | Name | Source | Unit | State Class | Notes |
|-----------|------|--------|------|-------------|-------|
| `sensor.irrisense_status` | Status | `workInfo.status` | — | — | Idle / Irrigating / Unavailable |
| `sensor.irrisense_current_zone` | Current Zone | `workInfo` + map lookup | — | — | Zone name when irrigating, "—" when idle |
| `sensor.irrisense_run_time` | Run Time | `workInfo.time` | min | measurement | Elapsed time of current run |
| `sensor.irrisense_progress` | Progress | `workInfo.progress` | % | measurement | Completion % of current run |
| `sensor.irrisense_water_pressure` | Water Pressure | `workInfo.waterpress` | PSI | measurement | Real-time water pressure |
| `sensor.irrisense_firmware` | Firmware | `DevInfo.version` | — | — | Diagnostic, firmware version string |
| `sensor.irrisense_next_run` | Next Run | `WrPlanOverview` + plan details | — | — | Next scheduled run time (computed from plan data) |
| `sensor.irrisense_valve` | Valve | `workInfo.valve` | — | measurement | Current valve number |

### Binary Sensors

| Entity ID | Name | Source | Device Class | Notes |
|-----------|------|--------|-------------|-------|
| `binary_sensor.irrisense_irrigating` | Irrigating | `workInfo.status` | running | ON when status=1 |
| `binary_sensor.irrisense_rain_detected` | Rain Detected | `Alarm.warnCode` | moisture | ON when rain warnCode bit set |
| `binary_sensor.irrisense_water_shortage` | Water Shortage | `Alarm.warnCode` | problem | ON when hydropenia warnCode bit set |
| `binary_sensor.irrisense_connected` | Connected | BLE connection state | connectivity | ON when reachable |

### Switches

| Entity ID | Name | Source | Notes |
|-----------|------|--------|-------|
| `switch.irrisense_rain_sensor` | Rain Sensor | `GetSenseSwitch` / `SetSenseSwitch` type=2 | Physical rain sensor hardware |
| `switch.irrisense_weather_rain` | Weather Rain | `GetSenseSwitch` / `SetSenseSwitch` type=0 | Cloud-based rain forecast skip |
| `switch.irrisense_weather_wind` | Weather Wind | `GetSenseSwitch` / `SetSenseSwitch` type=1 | Cloud-based wind forecast skip |
| `switch.irrisense_plan_{id}` | Plan: {zone} {time} {days} {depth} | `WrPlanBatchEdit` | Per-plan enable/disable (dynamic, see below) |
| `switch.irrisense_all_schedules` | All Schedules | `WrPlanBatchEdit` | Global enable/disable for all plans |

#### Dynamic Plan Switches

A switch entity is created for each irrigation plan configured on the device. These entities are **dynamic** — they track plans created, renamed, and deleted in the phone app.

- **Stable identity:** Each plan has a numeric `plan_id` from the device. The entity `unique_id` is `{address}-plan-{plan_id}`, so the entity survives renames and schedule changes.
- **Descriptive name:** The entity's friendly name is composed from zone name, start time, abbreviated weekdays, and depth — e.g. `Plan: North Side 7:30 MWF 0.25in`. This makes each plan visually distinct even when multiple plans target the same zone. Updated each poll cycle.
- **Weekday abbreviation:** `M T W Th F Sa Su` or `Daily` when all seven days are selected.
- **Extra state attributes:** Each plan switch exposes additional details as entity attributes for use in automations and dashboards:

  | Attribute | Type | Description |
  |-----------|------|-------------|
  | `plan_id` | int | Device-assigned plan identifier |
  | `zone_name` | str | Target zone/area name |
  | `zone_id` | int | Target zone identifier |
  | `start_time` | str | Scheduled start time (HH:MM) |
  | `weekdays` | str | Abbreviated schedule (e.g. "MWF", "Daily") |
  | `weekdays_raw` | list[int] | Raw weekday codes (0=Sun, 1=Mon, ..., 6=Sat) |
  | `depth_inches` | float | Water depth target in inches |
  | `point_time_minutes` | int | Minutes per irrigation point |
  | `estimated_time_minutes` | int | Estimated total run time |
  | `repeat_type` | int | Recurrence pattern code |

- **New plans:** Discovered on the next `WrPlanOverview` fetch. The coordinator signals the switch platform to register new entities via `async_add_entities`.
- **Deleted plans:** Entity becomes unavailable. Removed from the entity registry on the following poll cycle.
- **Latency:** Plan changes made in the phone app appear in HA within ~10 minutes (the zone discovery interval).

**Protocol:** `WrPlanBatchEdit` with body `{"enable_plans": [plan_id]}` or `{"disable_plans": [plan_id]}`. Supports multiple IDs per call, which is used by the global switch.

#### Global "All Schedules" Switch

A synthetic switch that enables or disables all plans at once. There is no native "global disable" command on the device — this switch sends a single `WrPlanBatchEdit` with all known plan IDs.

- **ON:** `{"enable_plans": [id1, id2, ...]}`
- **OFF:** `{"disable_plans": [id1, id2, ...]}`
- **State:** ON if any plan is enabled, OFF if all plans are disabled
- **Use case:** Vacation mode, seasonal shutdown, or quick disable before maintenance

### Actions (modeled after `vacuum` entity actions)

Actions mirror the [vacuum integration's action list](https://www.home-assistant.io/integrations/vacuum/#list-of-actions) where applicable.

| Action | Vacuum Equivalent | Command | Description |
|--------|-------------------|---------|-------------|
| `aiper.start` | `vacuum.start` | `setWorkMode` mode=1, status=1 | Start or resume irrigation |
| `aiper.stop` | `vacuum.stop` | `setWorkMode` mode=0, status=0 | Stop current irrigation |
| `aiper.pause` | `vacuum.pause` | `setWorkMode` mode=0, status=0 | Pause irrigation (device treats as stop) |
| `aiper.water_area` | `vacuum.clean_area` | `setWorkMode` per segment | Irrigate specific zones via area mapping (see parameters below) |
| `aiper.turn_on` | `vacuum.turn_on` | `WrPlanBatchEdit` enable all | Enable all schedules |
| `aiper.turn_off` | `vacuum.turn_off` | `WrPlanBatchEdit` disable all | Disable all schedules |
| `aiper.toggle` | `vacuum.toggle` | — | Toggle between turn_on / turn_off |
| `aiper.send_command` | `vacuum.send_command` | any | Send a raw BLE command (for advanced use / debugging) |

**Not applicable** (no irrigation equivalent):

| Vacuum Action | Reason |
|---------------|--------|
| `vacuum.return_to_base` | No dock — device is stationary |
| `vacuum.clean_spot` | No equivalent — zones are pre-mapped |
| `vacuum.locate` | No buzzer/LED confirmed in protocol |
| `vacuum.set_fan_speed` | Water pressure is read-only (sensor, not controllable) |
| `vacuum.start_pause` | Deprecated in favor of separate `start` / `pause` |

#### Entity Feature Flags

```python
class IrriSenseEntityFeature(IntFlag):
    START = 1
    STOP = 2
    PAUSE = 4
    WATER_AREA = 8
    TURN_ON = 16
    TURN_OFF = 32
    TOGGLE = 64
    SEND_COMMAND = 128
```

#### `water_area` Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `segment_ids` | list[str] | Yes (or via area target) | — | Zone IDs to irrigate |
| `water_yield` | float | No | 0.25 | Water yield rate: `0.1`, `0.25`, or `0.5` |
| `point_time` | int | No | 1 | Minutes per point (type 2 maps only): `1`, `5`, or `10` |

The integration sends a `setWorkMode` command per segment with `mode=0` (normal, no pesticide) and `status=1` (start). Pesticide-related fields (`pesticides_sn`, `used_amount`, `mode=1`) are out of scope for v1.

#### Zone Segments (modeled after `vacuum.clean_area`)

Zones are exposed as **segments** following the same pattern as `vacuum.clean_area` / `async_clean_segments`:

```python
@dataclass(slots=True)
class IrriSenseSegment:
    id: str          # map_id from WrMapManageOverView (stable numeric ID)
    name: str        # user-assigned zone name
    group: str | None = None  # zone type (e.g., "lawn", "garden")
```

**Integration methods:**

| Method | Vacuum Equivalent | Description |
|--------|-------------------|-------------|
| `async_get_segments()` | `async_get_segments()` | Returns current zones from cached `WrMapManageOverView` data |
| `async_water_segments(segment_ids)` | `async_clean_segments(segment_ids)` | Sends `setWorkMode` for each zone ID |
| `last_seen_segments` | `last_seen_segments` | Zones at last area mapping — detects zone re-mapping |
| `async_create_segments_issue()` | `async_create_segments_issue()` | Creates repair issue when zones change |

**Segment → HA Area mapping:** Users map IrriSense zones to HA Areas in the UI (Settings > Devices > Entities > "Map irrigation zones to areas"). Once mapped, `aiper.water_area` can be called targeting an `area_id` and the integration resolves it to the correct zone segment ID.

**Zone stability:** Zone IDs (`map_id`) can change if the user re-maps zones in the phone app. The `last_seen_segments` / repair issue pattern (same as vacuum) handles this — if segments change, a repair prompts the user to re-map.

### Number Entities (future)

| Entity ID | Name | Source | Range | Notes |
|-----------|------|--------|-------|-------|
| `number.irrisense_water_depth` | Water Depth | plan config | 0.1–1.0 | Per-zone water depth target |

### Diagnostic Entities

| Entity ID | Name | Source | Notes |
|-----------|------|--------|-------|
| `sensor.irrisense_model` | Model | `DevInfo.model` | Device model string |
| `sensor.irrisense_serial` | Serial Number | `DevInfo.sn` | Device serial number |
| `sensor.irrisense_rssi` | BLE RSSI | BLE connection | Signal strength at last poll |

---

## 3. Config Flow

### Discovery

The integration registers for passive BLE discovery via `manifest.json`:

```json
{
  "bluetooth": [
    {"local_name": "Aiper-WR-*"},
    {"local_name": "Aiper_WR_*"},
    {"local_name": "Aiper-IrriSense*"}
  ]
}
```

When HA sees a matching advertisement, it offers the integration to the user.

### Setup Steps

1. **Discovery** — HA detects IrriSense BLE advertisement
2. **Confirm** — User confirms device (shows name, MAC, RSSI)
3. **Connect test** — Integration connects, sends `DevInfo`, shows model/firmware/serial
4. **Done** — Device added, coordinator starts polling

No credentials needed — BLE proximity is the authentication.

### Options Flow

| Option | Default | Description |
|--------|---------|-------------|
| Idle poll interval | 60s | How often to poll when not irrigating |
| Active poll interval | 15s | How often to poll during irrigation |
| Unavailable timeout | 300s | How long before marking device unavailable |

---

## 4. Technical Details

### BLE Connection Management

Uses HA's `bluetooth` integration which provides:
- **`BleakClientWithServiceCache`** — wraps bleak with service caching
- **Transparent proxy support** — same API for local and ESPHome adapters
- **Connection slot management** — prevents BLE adapter exhaustion
- **Automatic adapter selection** — picks the adapter with best RSSI

Key constraints:
- Max MTU negotiation: 512 (device may accept less)
- Max chunk size: 152 bytes per write
- Write type: write-without-response (fastest, no ACK per chunk)
- Response timeout: 10 seconds per command

### Notification Handling

All responses arrive on NUS TX (`6e400003-...`). The handler must:

1. Buffer incoming bytes until `\n` delimiter
2. Base64 decode → XOR decrypt → JSON parse
3. Check response type against pending command
4. If match: deliver as command response
5. If unsolicited (`realTimeProgress`, `AbnormalReminder`, `Alarm`): process as event

During a poll cycle, unsolicited notifications can arrive between commands. These are captured and used to update entity state alongside command responses.

### Data Model

The coordinator maintains a single state dict updated each poll cycle:

```python
@dataclass
class IrriSenseState:
    # DevInfo
    model: str
    serial: str
    firmware: str

    # workInfo
    status: int          # 0=idle, 1=irrigating
    valve: int
    rotate: int
    water_pressure: float

    # workInfo (during irrigation)
    current_zone: str | None
    run_time: int
    progress: int

    # Alarm
    warn_code: int

    # GetSenseSwitch
    rain_sensor: bool
    weather_rain: bool
    weather_wind: bool

    # Computed
    is_irrigating: bool
    rain_detected: bool
    water_shortage: bool

    # Connection
    rssi: int | None
    available: bool
```

### Zone Discovery & Segment Management

On first connect and periodically (every 10 minutes while idle):

1. Send `WrMapManageOverView` → get list of zones with IDs, names, types
2. Build `IrriSenseSegment` list for `async_get_segments()` and area mapping
3. Compare against `last_seen_segments` — if changed, call `async_create_segments_issue()` to prompt re-mapping
4. Fetch `WrPlanOverview` + `WrPlanDetail` for schedule display and plan switch entities

Zone details (individual points) are not fetched during normal polling — they're only needed for map display which is not an HA concern.

### Error Handling

| Error | Behavior |
|-------|----------|
| BLE connection timeout | Mark unavailable, backoff to 120s polling |
| Command timeout (10s) | Skip that command, continue cycle with remaining commands |
| Parse error on response | Log warning, skip that response |
| Device returns `res: -1` | Log as command failure, entity shows last known state |
| MTU negotiation failure | Fall back to 300, then 20 (minimum BLE MTU) |

### Plan/Schedule Representation

Irrigation schedules are read-only in v1 (editing plans is complex and risky over BLE). The integration exposes:

- **Next run sensor** — computed from `WrPlanDetail.time_ctrl` (weekdays + start_time) using local timezone
- **Plan attributes** — each plan's name, zone, schedule, enabled status exposed as sensor attributes

Future versions could add a calendar entity or schedule editing via services.

---

## 5. Out of Scope (v1)

These features are deferred to future versions:

| Feature | Reason |
|---------|--------|
| Schedule editing | Complex plan config, high risk of misconfiguration |
| Map/zone editing | Requires physical presence at device during mapping |
| Pesticide management | Niche feature, needs more protocol research |
| Irrigation history | Requires cloud REST API auth (separate integration concern) |
| Winter drainage mode | Seasonal, destructive operation — needs careful UX |
| Pool robot support | Different device family, different UUIDs/commands, separate integration |
| Nozzle type switching | Low priority, rarely changed |

---

## 6. Dependencies

| Dependency | Purpose | Notes |
|------------|---------|-------|
| `bleak` | BLE communication | Included with HA |
| `bluetooth` (HA) | BLE discovery + proxy support | Core HA integration |
| `homeassistant` | HA framework | Core |

No additional Python packages needed. The protocol layer (XOR, Base64, JSON) uses only stdlib.
