# Aiper IrriSense 2 BLE API Specification

**Reverse-engineered from:** Aiper Android App v3.3.2 (com.aiper.link)
**Date:** 2026-05-28
**Purpose:** Reference for Home Assistant integration via BLE proxies
**Device:** IrriSense 2 (WR device type) - smart irrigation controller

---

## Table of Contents

1. [Device Identification](#1-device-identification)
2. [BLE Connection](#2-ble-connection)
3. [Protocol Differences from Pool Robots](#3-protocol-differences-from-pool-robots)
4. [Command Reference](#4-command-reference)
5. [Device State & Subscriptions](#5-device-state--subscriptions)
6. [Home Assistant Entity Mapping](#6-home-assistant-entity-mapping)
7. [Implementation Example](#7-implementation-example)

---

## 1. Device Identification

### Models and Serial Number Prefixes

| Model Name | SN Prefix | DeviceType |
|------------|-----------|------------|
| IrriSense WR | WR | WR |
| Irrigo WR | WR | WR |
| IrriSense 2 | WR | WR |
| IrriSense N2 | WG | WR |
| IrriSense II | WC | WR |
| IrriSense 2 Chromatic | WC | WR |
| IrriSense 2 SE | WL | IrriSenseSE |
| IrriSense2SE | WL | IrriSenseSE |

### BLE Advertisement Name

Format: `Aiper-<MODEL>-<SUFFIX>` or `Aiper_<MODEL>_<SUFFIX>`

Example: `Aiper-WR-A1B2C3`

The model segment (e.g., "WR") is extracted by splitting on `-` or `_` and taking the second part.

### Series Groupings

- **IrriSenses:** WR, IrriSenseSE
- **X9Series:** WR and IrriSenseSE are also members of the X9Series grouping (affects command format)

---

## 2. BLE Connection

### GATT UUIDs - Nordic UART Service (NUS)

The IrriSense 2 uses standard Nordic UART Service UUIDs, different from pool robots:

```
Service:  6e400001-b5a3-f393-e0a9-e50e24dcca9e
Write:    6e400002-b5a3-f393-e0a9-e50e24dcca9e  (NUS RX characteristic)
Notify:   6e400003-b5a3-f393-e0a9-e50e24dcca9e  (NUS TX characteristic)
```

These are well-known UUIDs for Nordic BLE UART and are widely supported.

### Connection Parameters

| Parameter | Value |
|-----------|-------|
| MTU request | 512 (primary) / 300 (fallback) |
| Max chunk size | **152 bytes** (smaller than pool robots' 200) |
| Connection timeout | 10,000 ms |
| Write timeout | 5,000 ms |
| Encryption | XOR (key: `[0x12, 0x34, 0x56, 0x78]`) |

### Connection Flow

1. Scan for BLE device with name starting with `"Aiper"` and model `"WR"`
2. Connect to the device
3. Discover Nordic UART Service (`6e400001-...`)
4. Get RX characteristic (`6e400002-...`) for writes
5. Get TX characteristic (`6e400003-...`) for notifications
6. Request MTU 512
7. Enable notifications on TX characteristic
8. Device is ready for commands

---

## 3. Protocol Differences from Pool Robots

The IrriSense 2 has several important differences from pool robot devices:

| Aspect | Pool Robots | IrriSense 2 |
|--------|-------------|-------------|
| BLE UUIDs | Custom Aiper UUIDs | Nordic UART Service |
| Max chunk size | 200 bytes | **152 bytes** |
| CRC checksum | Included | **Skipped** (no `chksum` field) |
| Command format | `{"type":"X","data":{}}` | `{"X":{}}` (X9 Series format) |
| Encryption | XOR or ECDH | XOR only |

### Command Format (X9 Series Style)

Because WR is part of the X9Series, commands use the flat format:

```json
{"<CommandType>": <data>}
```

**Not** the standard `{"type":"X","data":{}}` format used by most pool robots.

### No CRC Checksum

IrriSense devices explicitly skip the CRC16-Modbus checksum. The `chksum` field is **not** included in commands. This is confirmed in `CmdFactory.java` line 166:

```java
if (isEncrypt && !companion.getIrriSenses().contains(deviceType)) {
    mutableMapOf.put("chksum", Long.valueOf(crc16(jsonString)));
}
```

### Encryption

The IrriSense 2 uses XOR encryption only (not ECDH):

```
Outbound: json_bytes -> XOR([0x12,0x34,0x56,0x78]) -> Base64 -> append "\n"
Inbound:  strip "\n" -> Base64 decode -> XOR([0x12,0x34,0x56,0x78]) -> JSON
```

---

## 4. Command Reference

### Core Device Commands

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `DevInfo` | Query | none | Device information (firmware, model, serial) |
| `OpInfo` | Query | none | Operational info / online status |
| `NetStat` | Query | none | Network/connectivity status |
| `TimeZoneSet` | Set | see [TimeZoneSet](#timezoneset) | Set device timezone |
| `FactoryRestore` | Set | none | Reset to factory defaults |

#### TimeZoneSet

```json
{
  "timeZone": "UTC+8",
  "time": "2026-05-28,14:30:00,4",
  "zoneId": "America/New_York",
  "utcOffset": "UTC-5"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `timeZone` | string | UTC offset string (e.g., `"UTC+8"`, `"UTC-5:30"`) |
| `time` | string | Current time: `"yyyy-MM-dd,HH:mm:ss,D"` where D = day-of-week (1-7, Sunday may be 0) |
| `zoneId` | string | Java/IANA timezone ID (e.g., `"America/New_York"`) |
| `utcOffset` | string | UTC offset hours as string (e.g., `"UTC-5"`) |

### Irrigation Control

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `setWorkMode` | Set | see [setWorkMode](#setworkmode) | Start/stop irrigation, set mode |
| `workInfo` | Query | none | Get current work status/progress |
| `WrControl` | Set | `{"cmd": 0\|1}` | Manual control (0=stop, 1=start) |
| `realtimeStatus` | Set/Subscribe | `{"cmd": <int>}` | Subscribe to real-time sprinkler position |
| `realTimeProgress` | Set/Subscribe | `{"cmd": <int>}` | Subscribe to real-time watering progress |

#### setWorkMode

**WARNING:** Do NOT send `setWorkMode` without a `map_id`. Tested on V3.8.6: starting without a zone causes garbage `map_id` (134218851), map anomaly errors, and a glitched device state that's hard to stop. Always use the full form with a valid `map_id`.

**Stop:**

```json
{"mode": 0, "status": 0}
```

**Also try `WrControl` to stop:**
```json
{"cmd": 0}
```

**Full form** (start with zone/map selection):

When starting irrigation on a specific map zone, the app sends a richer payload:

```json
{
  "map_id": 12345,
  "status": 1,
  "mode": 0,
  "waterYield": 0.25
}
```

| Field | Type | Description |
|-------|------|-------------|
| `map_id` | long | Map/zone ID from MappingRegion |
| `status` | int | Always `1` (start) |
| `mode` | int | `0` = normal (no pesticide), `1` = with pesticide |
| `waterYield` | float | Water yield rate (0.1, 0.25, or 0.5 depending on settings) |
| `point_time` | int | (Type 2 maps only) Time per point: `1`, `5`, or `10` minutes |
| `pesticides_sn` | string | (Pesticide mode) Serial number of pesticide cartridge |
| `used_amount` | float | (Pesticide mode) Amount of pesticide to use |

**Mode logic:**
- `mode = 0` when no pesticide cartridge SN is present
- `mode = 1` when a pesticide cartridge SN is provided
- For map type 2: uses `point_time` instead of `waterYield`
- For map type 0 with pesticide: `waterYield` is forced to `0.1`

### Water Management

| Command | Direction | Parameters | Description | Firmware |
|---------|-----------|------------|-------------|----------|
| `setWaterYield` | Set | `{"value": <float>}` | Set water output/yield | Untested |
| `getWaterYield` | Query | none | Get current water yield setting | **No response on V3.8.6** |
| `setWeekWaterYield` | Set | `{"value": <float>}` | Set weekly water depth target | Untested |
| `getWeekWaterYield` | Query | none | Get weekly water depth target | **No response on V3.8.6** |

### Nozzle Management

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `getNozzle` | Query | none | Get current nozzle type setting |
| `setNozzle` | Set | `{"value": 0\|1}` | Set nozzle type (0 = standard, 1 = jet) |
| `nozzleSwitch` | Query | none | Query nozzle switch state |

**Nozzle types:**
- `0` = Standard nozzle
- `1` = Jet nozzle

### Zone/Map Management

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `GetWrMap` | Query/Subscribe | none | Get full irrigation zone map (**no response on V3.8.6**) |
| `SetWrMap` | Set | map data | Set irrigation zone map |
| `WrMapBuildStart` | Set | `{"type": <int>}` | Start mapping/zone creation |
| `WrMapBuildSave` | Set | see [Map Point Upload](#map-point-upload-wrmapbuildsave) | Save a single point during map build |
| `WrMapBuildEdit` | Set | edit data | Edit existing map |
| `WrMapBuildExit` | Set | `{"type": 0}` | Exit map building mode |
| `WrMapBuildExitReport` | Subscribe | none | Abnormal exit notification during map building |
| `WrMapManageOverView` | Query | none | Get overview of all maps |
| `WrMapManageSingleInfo` | Query | `{"id": <long>, "type": <int>, "point_index": <int>}` | Get a single point from a map |
| `WrMapSetName` | Set | `{"name": "..."}` | Rename a map/zone |
| `setIrrgatePoint` | Set | `{"valve": <int>, "rotate": <int>}` | Set irrigation waypoint |
| `locationGet` | Query | none | Get device location |
| `locationSet` | Set | `{"latitude": <f>, "longitude": <f>}` | Set device location |

#### Map Limits

- **WR models:** Up to **10** map areas
- **IrriSense 2 SE (WL) models:** Up to **5** map areas

#### Map Data Structures

**MappingRegion** (returned by `GetWrMap`, `WrMapManageSingleInfo`):

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Map/zone name |
| `type` | int | Map type classification |
| `id` | long | Unique map identifier |
| `points` | list | Array of MapLocation objects |
| `flags` | int | Status flags (bit 0 = locally modified) |

**MapLocation** (each point within a MappingRegion):

| Field | Type | JSON key | Description |
|-------|------|----------|-------------|
| `x` | float | `x` | X coordinate |
| `y` | float | `y` | Y coordinate |
| `valve` | int | `valve` | Valve number/ID |
| `rotate` | int | `rotate` | Rotation angle (degrees) |
| `waterPressure` | float | `waterpress` | Water pressure setting |

**RegionMappingFormDevice** (returned by `WrMapManageOverView`):

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Map/zone name |
| `type` | int | Map type |
| `id` | long | Unique map ID |
| `count` | int | Number of points in the map |

#### Map Query Flow

1. Send `WrMapManageOverView` to get a list of all maps (names, IDs, point counts)
2. For each map, iterate `point_index` from `0` to `point_total - 1`:
   - Send `WrMapManageSingleInfo` with `{"id": <id>, "type": <type>, "point_index": <i>}`
   - Response includes `point_info` with valve, rotate, waterpress, x, y, num
3. `GetWrMap` appears unsupported on firmware V3.8.6 (times out)

#### Map Point Upload (WrMapBuildSave)

Each point is uploaded individually during map building:

```json
{
  "name": "Zone 1",
  "id": 12345,
  "type": 0,
  "num": 0,
  "x": 150,
  "y": 200,
  "rotate": 90,
  "waterpress": 1.5,
  "valve": 1,
  "total": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Map name |
| `id` | long | Map ID |
| `type` | int | Map type |
| `num` | int | Point index (0-based) |
| `x` | int | X coordinate (cast from float) |
| `y` | int | Y coordinate (cast from float) |
| `rotate` | int | Rotation angle |
| `waterpress` | float | Water pressure |
| `valve` | int | Valve number |
| `total` | int | Total number of points being uploaded |

The app retries each point upload up to **10 times** on failure.

#### Map Building Flow

1. Send `WrMapBuildStart` with `{"type": <int>}` to enter build mode
2. Subscribe to `WrMapBuildExitReport` for abnormal exit events
3. For each point, send `WrMapBuildSave` with the point data (see above)
4. When complete, the app marks `isComplete = true`
5. On exit, send `WrMapBuildExit` with `{"type": 0}` to stop
6. If map was not fully uploaded, the app unsubscribes from real-time status

`WrMapBuildStart` response codes:
- `0`, `5`, `6` — success (proceed with point upload)
- `3`, `4` — cannot create map (throws error)
- Other — general error

### Schedule/Task Management

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `getWRWeekdayTaskList` | Query | none | Get all weekly schedule tasks (**no response on V3.8.6**) |
| `WRWeekdayTaskEdit` | Set | see [Task Edit](#task-edit-wrweekdaytaskedit) | Create/edit a weekly task |
| `WRWeekdayTaskEnabled` | Set | see [Task Enable](#task-enable-wrweekdaytaskenabled) | Enable/disable a task |
| `WRWeekdayTaskSkip` | Set | `{"id": <int>, "timeId": <int>, "date": "..."}` | Skip a scheduled task occurrence |

#### Task Data Structures

**Task** (returned by `getWRWeekdayTaskList`):

| Field | Type | Description |
|-------|------|-------------|
| `taskId` | long | Unique task identifier (`-1` = new/unsaved task) |
| `dayOfWeek` | int | Day of week: `0` = Monday, `6` = Sunday |
| `enabled` | int | `0` = disabled, `1` = enabled |
| `repeatEveryWeek` | int | `0` = one-time, `1` = repeats weekly |
| `taskTimeList` | list | Array of TaskTime objects |
| `flag` | int | UI state (0 = unselected, 1 = selected) |

**TaskTime** (each scheduled time within a task):

| Field | Type | Description |
|-------|------|-------------|
| `taskTimeId` | long | Unique time slot identifier |
| `timeType` | int | `1` = morning, `2` = afternoon |
| `startTime` | string | Time in `"HH:MM"` format (e.g., `"06:00"`) |

#### Task Edit (WRWeekdayTaskEdit)

```json
{
  "tasks": [
    {
      "id": 1,
      "week": 0,
      "times": {"1": "06:00", "2": "18:00"},
      "DTimes": [],
      "enabled": 1,
      "repeat": 1
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tasks` | list | Array of task objects to create/edit |
| `tasks[].id` | int | Task ID (`dayOfWeek + 1`, range 1-7 for Mon-Sun) |
| `tasks[].week` | int | Day of week (0-6, 0 = Monday) |
| `tasks[].times` | object | Time slots: key = timeType as string (`"1"` or `"2"`), value = `"HH:MM"` |
| `tasks[].DTimes` | list | Time type IDs to delete (e.g., `[1]` to remove morning slot) |
| `tasks[].enabled` | int | `0` = disabled, `1` = enabled |
| `tasks[].repeat` | int | `0` = one-time, `1` = repeat weekly |

#### Task Enable (WRWeekdayTaskEnabled)

```json
{
  "taskId": 123456789,
  "enabled": 1,
  "repeat": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `taskId` | long | Task ID from the task object |
| `enabled` | int | `0` = disable, `1` = enable |
| `repeat` | int | Current repeat setting (preserved from the task) |

### Plan Management (V3.8.6+ — replaces WRWeekdayTask commands)

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `WrPlanOverview` | Query | none | Get used/available plan IDs (up to 40 slots) |
| `WrPlanDetail` | Query | `{"plan_id": <int>}` | Get full details of a specific plan |
| `WrPlanConfig` | Set | see [Plan Config](#plan-config-wrplanconfig) | Create/edit an irrigation plan |
| `WrPlanBatchEdit` | Set | batch data | Batch edit multiple plans |
| `WrPlanBatchDelete` | Set | batch ids | Batch delete plans |

#### WrPlanOverview Response (confirmed V3.8.6)

```json
{
  "used_ids": [1],
  "available_ids": [2, 3, ...],
  "total_used": 1,
  "total_available": 39
}
```

#### WrPlanDetail Response (confirmed V3.8.6)

```json
{
  "plan_id": 1,
  "work_type": 0,
  "plan_used_total": 1,
  "map_info": {
    "name": "Rhodo",
    "type": 0,
    "id": 3
  },
  "work_ctrl": {
    "depth": 0.4,
    "point_time": 1
  },
  "time_ctrl": {
    "start_time": "08:00",
    "repeat_type": 1,
    "weekdays": [1, 3, 5]
  },
  "enabled": true,
  "estimated_time": 25
}
```

| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | int | Plan slot ID (1-40) |
| `work_type` | int | Work type (0 = normal) |
| `plan_used_total` | int | Total plans in use |
| `map_info.name` | string | Zone name |
| `map_info.type` | int | Map type |
| `map_info.id` | long | Map ID |
| `work_ctrl.depth` | float | Water depth target (inches) |
| `work_ctrl.point_time` | int | Time per point (minutes) |
| `time_ctrl.start_time` | string | Start time `"HH:MM"` |
| `time_ctrl.repeat_type` | int | `1` = repeat weekly |
| `time_ctrl.weekdays` | list[int] | Days of week (1=Mon, 7=Sun) |
| `enabled` | bool | Whether plan is active |
| `estimated_time` | int | Estimated runtime (minutes) |

#### Plan Config (WrPlanConfig)

From decompiled app — used to create/edit plans:

```json
{
  "plan_id": 1,
  "type": 0,
  "work_type": 0,
  "map_id": 3,
  "work_ctrl": {
    "water_depth": 0.4,
    "point_time": 1
  },
  "time_ctrl": {
    "start_time": "08:00",
    "weekdays": [1, 3, 5],
    "repeat_type": 1
  },
  "enabled": true
}
```

### Weather/Sensor Integration

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `GetSenseSwitch` | Query | none | Get rain/weather sensor settings |
| `SetSenseSwitch` | Set | `{"type": <int>, "status": <int>}` | Enable/disable a sensor type |

#### SetSenseSwitch

```json
{"type": 2, "status": 1}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | int | Sensor type: `0` = weather rain, `1` = weather wind, `2` = rain sensor |
| `status` | int | `0` = disable, `1` = enable |

**Sensor types:**
- `0` — Weather rain detection (cloud-based rain forecast)
- `1` — Weather wind detection (cloud-based wind forecast)
- `2` — Physical rain sensor (hardware sensor on device)

**GetSenseSwitch response** (EnabledSnapshot):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rainSensing` | int | 1 | Physical rain sensor enabled |
| `weatherRain` | int | 1 | Weather rain detection enabled |
| `weatherWind` | int | 1 | Weather wind detection enabled |
| `flag` | int | 16 | Feature flags |

### Pesticide/Solution Management

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `GetWrPesticides` | Query | none | Get pesticide/solution status |
| `GetWrPesticidesInfo` | Query | none | Get pesticide details |
| `GetWrPesticidesAck` | Set | ack data | Acknowledge pesticide notification |
| `WrPesticidesMsg` | Set/Query | message data | Pesticide messaging |

### Records & History

Irrigation history uses a **hybrid BLE + cloud** architecture. The app syncs records from the device to the cloud, then displays history from the REST API. Once synced, records are cleared from the device.

#### BLE Commands

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `WrRecordOverView` | Query | none | Get IDs of unsynced records on device (empty if all synced) |
| `WrRecordSync` | Set | `{"ids": [<int>, ...]}` | Mark record IDs as synced on device |

**Note:** `WrRecordOverView` returns `{"ids": []}` when all records have already been uploaded to the cloud. Individual unsynced records can be fetched by index before syncing.

#### Cloud REST API (requires Aiper account auth)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/wr/wateringRecordStatisticsV2` | GET | Summary: total run count, total gallons, water savings |
| `/wr/getWateringRecordHistoryDataV2` | GET | Paginated history (15/page): area, duration, water consumption per run |
| `/wr/batchWateringRecordReportV2` | POST | Upload synced device records to cloud |

#### Record Data Model (IrrigationRecordBean — from REST API)

| Field | Type | Description |
|-------|------|-------------|
| `id` | long | Record ID |
| `sn` | string | Device serial number |
| `regionName` | string | Zone/area name |
| `regionId` | int | Zone ID |
| `regionType` | int | Zone type |
| `area` | float | Area covered (m²) |
| `depth` | float | Water depth applied |
| `duration` | int | Run time (seconds) |
| `startTimestamp` | long | Start time (Unix ms) |
| `mode` | int | Work mode |
| `taskStatus` | int | Completion status |
| `newWaterYield` | float | Water yield rate |
| `usedVolume` | double | Water consumption (gallons) |
| `waterSavingAmount` | float | Water saved vs traditional |
| `warnCode` | int | Warning/error code |
| `workType` | int | Work type |

#### Record Data Model (IrrisenseTaskRecordSnapshot — from BLE device)

| Field | Type | Description |
|-------|------|-------------|
| `id` | long | Record ID |
| `map_info` | object | Zone details: area ID, name, type |
| `run_info` | object | Execution: area, duration, timestamp, water consumption (`wate_consump`), depth, homogeneity, error code |
| `work_params` | object | Work configuration parameters |
| `liquid_info` | object | Pesticide/solution details (optional) |

#### Record Sync Flow

1. App sends `WrRecordOverView` via BLE → gets list of unsynced record IDs
2. For each ID, app fetches record detail via BLE
3. App sends `WrRecordSync` with the IDs to mark them synced on device
4. App uploads records to cloud via `/wr/batchWateringRecordReportV2`
5. Subsequent `WrRecordOverView` calls return empty

#### HA Integration Implications

- **Historical data** requires REST API access (Aiper account authentication)
- **Real-time data** can be captured via BLE notifications (`IrrigatingRecordReport`) during/after watering
- Unsynced records on the device can be read before the app syncs them

### Winter/Drainage Mode

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `WrDrainExit` | Set | `{"type": <int>}` | Control winter drainage mode |

### Alarm

| Command | Direction | Parameters | Description |
|---------|-----------|------------|-------------|
| `Alarm` | Query/Subscribe | none | Get/subscribe to alarm notifications |

---

## 5. Device State & Subscriptions

### Shadow Model

The IrriSense reports state through the same Shadow model as pool robots. Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `mode` | int | Current operating mode |
| `status` | int | Current device status |
| `warn` | int | Warning/alarm flags |
| `warn_code` | string | Warning code details |
| `link` | int | Connectivity status |

### Work Info State (confirmed V3.8.6)

Queried via `workInfo` command:

```json
{
  "status": 0,
  "valve": 47,
  "rotate": 0,
  "waterpress": 101.99
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | int | `0` = idle, `1` = running |
| `valve` | int | Current valve number |
| `rotate` | int | Sprinkler rotation angle |
| `waterpress` | float | Water pressure (PSI) |

### Real-Time Progress (confirmed V3.8.6)

**The device auto-pushes `realTimeProgress` notifications during irrigation** — these are unsolicited and arrive independently of any command sent. They contain rich operational data:

```json
{
  "status": 1,
  "mode": 0,
  "task_type": 1,
  "map_info": {
    "name": "Rhodo",
    "type": 0,
    "id": 3
  },
  "waterYield": 0.25,
  "point_time": 99,
  "progress": 0,
  "time": 6,
  "hydropenia": false,
  "x": -288,
  "y": 1123,
  "repairLayer": 0,
  "plan_id": 0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | int | `0` = stopped, `1` = running |
| `mode` | int | Work mode (0 = normal) |
| `task_type` | int | Task type (1 = manual start) |
| `map_info` | object | Active zone: name, type, id |
| `waterYield` | float | Water yield rate |
| `point_time` | int | Time per point |
| `progress` | int | Completion progress |
| `time` | int | Elapsed time (seconds) |
| `hydropenia` | bool | Water deficiency detected |
| `x` | int | Sprinkler X position |
| `y` | int | Sprinkler Y position |
| `repairLayer` | int | Repair layer indicator |
| `plan_id` | int | Plan ID (0 = manual start, >0 = scheduled plan) |

**Important for integration:** These notifications arrive on the same NUS TX characteristic as command responses. The integration must distinguish unsolicited notifications from command response by matching the response `type` field against the pending command. Any unmatched notification is an unsolicited event.

---

## 6. Home Assistant Entity Mapping

### Recommended Entities

| HA Entity Type | Command(s) | Description |
|---------------|------------|-------------|
| `switch.irrigation` | `setWorkMode`, `WrControl` | Start/stop irrigation |
| `sensor.work_status` | `workInfo` subscribe | Current operation status |
| `sensor.water_yield` | `getWaterYield` | Current water output rate |
| `number.weekly_water_depth` | `getWeekWaterYield` / `setWeekWaterYield` | Weekly watering target |
| `select.nozzle_type` | `getNozzle` / `setNozzle` | Active nozzle configuration |
| `switch.rain_sensor` | `GetSenseSwitch` / `SetSenseSwitch` | Rain delay feature |
| `binary_sensor.alarm` | `Alarm` subscribe | Active alarms |
| `sensor.device_info` | `DevInfo` | Firmware version, model |
| `calendar.schedule` | `getWRWeekdayTaskList` | Irrigation schedule |
| `button.skip_task` | `WRWeekdayTaskSkip` | Skip next scheduled run |
| `switch.winter_mode` | `WrDrainExit` | Winter drainage mode |

### Potential Additional Entities (if features present)

| HA Entity Type | Command(s) | Description |
|---------------|------------|-------------|
| `sensor.location` | `locationGet` | Device GPS coordinates |
| `switch.pesticide` | `GetWrPesticides` | Chemical dosing status |
| `sensor.watering_progress` | `realTimeProgress` | Live watering progress |

---

## 7. Implementation Example

### Python Pseudocode

```python
import base64
import json

XOR_KEY = bytes([0x12, 0x34, 0x56, 0x78])

# Nordic UART Service UUIDs for IrriSense 2
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write to this
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notifications from this

MAX_CHUNK = 152  # IrriSense uses smaller chunks than pool robots

def xor_crypt(data: bytes) -> bytes:
    """XOR encrypt/decrypt (symmetric)"""
    return bytes([b ^ XOR_KEY[i % 4] for i, b in enumerate(data)])

def build_command(cmd_type: str, data: dict = None) -> bytes:
    """Build an IrriSense command (X9 Series format, no CRC)"""
    # X9 Series format: {"<type>": <data>}
    cmd = {cmd_type: data or {}}
    # No chksum for IrriSense devices
    
    json_bytes = json.dumps(cmd, separators=(',', ':')).encode('utf-8')
    encrypted = xor_crypt(json_bytes)
    encoded = base64.b64encode(encrypted).decode('ascii') + "\n"
    return encoded.encode('utf-8')

def parse_response(accumulated: str) -> dict:
    """Parse an IrriSense response"""
    raw = base64.b64decode(accumulated.rstrip('\n'))
    decrypted = xor_crypt(raw)
    data = json.loads(decrypted.decode('utf-8'))
    
    # Normalize X9 format to standard format
    # X9 response: {"<type>": <data>} -> extract type and data
    for key in data:
        if key not in ('chksum', 'res'):
            return {'type': key, 'data': data[key]}
    return data

async def send_command(ble_client, cmd_type: str, data: dict = None):
    """Send a command to IrriSense 2 over BLE"""
    message = build_command(cmd_type, data)
    
    # Split into 152-byte chunks
    for i in range(0, len(message), MAX_CHUNK):
        chunk = message[i:i + MAX_CHUNK]
        await ble_client.write_gatt_char(NUS_RX_UUID, chunk)

# === Example Operations ===

# Query device info
await send_command(client, "DevInfo")

# Start irrigation (simple manual control)
await send_command(client, "WrControl", {"cmd": 1})

# Stop irrigation (simple manual control)
await send_command(client, "WrControl", {"cmd": 0})

# Start normal watering via setWorkMode
await send_command(client, "setWorkMode", {"mode": 0, "status": 1})

# Start watering a specific zone with water yield
await send_command(client, "setWorkMode", {
    "map_id": 12345,
    "status": 1,
    "mode": 0,
    "waterYield": 0.25
})

# Stop watering via setWorkMode
await send_command(client, "setWorkMode", {"mode": 0, "status": 0})

# Start vegetation mode
await send_command(client, "setWorkMode", {"mode": 3, "status": 1})

# Set weekly water depth target (in mm or inches)
await send_command(client, "setWeekWaterYield", {"value": 25.4})

# Get current work status
await send_command(client, "workInfo")

# Get irrigation schedule
await send_command(client, "getWRWeekdayTaskList")

# Create/edit a weekly task (water Mon at 6am and 6pm, repeating)
await send_command(client, "WRWeekdayTaskEdit", {
    "tasks": [{
        "id": 1,
        "week": 0,
        "times": {"1": "06:00", "2": "18:00"},
        "DTimes": [],
        "enabled": 1,
        "repeat": 1
    }]
})

# Enable/disable a task
await send_command(client, "WRWeekdayTaskEnabled", {
    "taskId": 123456789,
    "enabled": 0,
    "repeat": 1
})

# Skip a scheduled task
await send_command(client, "WRWeekdayTaskSkip", {
    "id": 1,
    "timeId": 2, 
    "date": "2026-05-28"
})

# Enable physical rain sensor
await send_command(client, "SetSenseSwitch", {"type": 2, "status": 1})

# Disable weather rain detection
await send_command(client, "SetSenseSwitch", {"type": 0, "status": 0})

# Set nozzle to jet type
await send_command(client, "setNozzle", {"value": 1})

# Set timezone
await send_command(client, "TimeZoneSet", {
    "timeZone": "UTC-5",
    "time": "2026-05-28,14:30:00,4",
    "zoneId": "America/New_York",
    "utcOffset": "UTC-5"
})

# Get zone map (full map data via subscribe)
await send_command(client, "GetWrMap")

# Get overview of all maps (names, IDs, point counts)
await send_command(client, "WrMapManageOverView")

# Get a specific map's full point data
await send_command(client, "WrMapManageSingleInfo", {"id": 12345, "type": 0})

# Start building a new map
await send_command(client, "WrMapBuildStart", {"type": 0})

# Upload a map point (repeat for each point)
await send_command(client, "WrMapBuildSave", {
    "name": "Front Yard",
    "id": 12345,
    "type": 0,
    "num": 0,
    "x": 150,
    "y": 200,
    "rotate": 90,
    "waterpress": 1.5,
    "valve": 1,
    "total": 5
})

# Exit map building mode
await send_command(client, "WrMapBuildExit", {"type": 0})

# Set a sprinkler waypoint
await send_command(client, "setIrrgatePoint", {"valve": 1, "rotate": 90})

# Enter winter drainage mode
await send_command(client, "WrDrainExit", {"type": 1})

# Get nozzle settings
await send_command(client, "getNozzle")

# Set timezone
# (uses CmdFactory.createTimeZoneData format)
await send_command(client, "TimeZoneSet")
```

### Notification Handler

```python
class IrriSenseNotificationHandler:
    def __init__(self):
        self.buffer = ""
    
    def handle_notification(self, sender, data: bytearray):
        """Called for each BLE notification from TX characteristic"""
        text = data.decode('utf-8')
        self.buffer += text
        
        if self.buffer.endswith('\n'):
            response = parse_response(self.buffer)
            self.buffer = ""
            self.dispatch(response)
    
    def dispatch(self, response: dict):
        cmd_type = response.get('type', '').lower()
        data = response.get('data', {})
        
        if cmd_type == 'devinfo':
            # Update device info entities
            pass
        elif cmd_type == 'workinfo':
            # Update work status
            pass
        elif cmd_type == 'alarm':
            # Handle alarm notification
            pass
        elif cmd_type == 'getwrmap':
            # Full map data — data contains MappingRegion list
            # Each region: {name, type, id, points: [{x, y, valve, rotate, waterpress}], flags}
            pass
        elif cmd_type == 'wrmapmanageoverview':
            # Map overview — list of {name, type, id, count}
            pass
        elif cmd_type == 'wrmapmanagesingleinfo':
            # Single map detail — MappingRegion with full points
            pass
        elif cmd_type == 'wrmapbuildexitreport':
            # Abnormal exit during map building
            pass
        # ... etc
```

---

## Appendix A: Cloud Transport (MQTT)

The IrriSense 2 also communicates via AWS IoT MQTT using the same XOR-encrypted JSON protocol as BLE. See `AIPER_BLE_API_SPEC.md` Section 11 for full details.

**Key facts for IrriSense:**
- Command topic: `aiper/things/{sn}/downChan`
- Response topic: `aiper/things/{sn}/upChan`
- Report topic: `aiper/things/{sn}/app/report` (X9 Series)
- Same XOR key `[0x12, 0x34, 0x56, 0x78]`, same JSON format, Base64-encoded
- **Multi-session limitation:** MQTT client ID is per-user (Cognito Identity ID). Only one client can be connected per account. A second connection disconnects the first.
- BLE and MQTT are independent — a device can be controlled via BLE while also connected to MQTT without conflict.

---

## Appendix B: AT Command Protocol

While the IrriSense 2 primarily uses JSON commands over BLE (as documented above), there is also an AT command protocol used in some contexts (particularly over MQTT):

### AT Command Format

```
Query:  AT+<NAME>
Set:    AT+<NAME>=<param1>,<param2>,...
```

### AT Response Format

```
Success:       +ok
Error:         +error
Subscription:  +<NAME>:<data1>,<data2>,...\r\n
```

### AT Command Transport

AT commands are wrapped in a JSON envelope:
```json
{"cmd": "AT+<NAME>=<params>", "sn": "<serial_number>"}
```

This JSON envelope is then encrypted/encoded the same way as regular commands. AT commands are mainly used for MQTT shadow reporting when the device is connected to WiFi, not typically for direct BLE control.
