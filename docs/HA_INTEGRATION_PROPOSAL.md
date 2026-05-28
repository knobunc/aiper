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

### Buttons

| Entity ID | Name | Command | Notes |
|-----------|------|---------|-------|
| `button.irrisense_stop` | Stop Irrigation | `setWorkMode` mode=0, status=0 | Emergency stop |

### Services (custom)

| Service | Parameters | Command | Notes |
|---------|-----------|---------|-------|
| `aiper.start_irrigation` | `zone_name` or `map_id`, `water_yield` (optional) | `setWorkMode` | Start irrigation on a specific zone |
| `aiper.stop_irrigation` | — | `setWorkMode` mode=0, status=0 | Stop current irrigation |

Using a custom service for start (rather than a button per zone) because the zone selection is dynamic — zones are user-configured and can change.

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

### Zone Discovery

On first connect and periodically (every 10 minutes while idle):

1. Send `WrMapManageOverView` → get list of zones with IDs, names, types
2. Cache zone list for service call validation and zone name display
3. Optionally fetch `WrPlanOverview` + `WrPlanDetail` for schedule display

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
