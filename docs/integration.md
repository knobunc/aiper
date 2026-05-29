# Aiper IrriSense Integration Documentation

## Overview

The Aiper IrriSense integration provides local control of Aiper IrriSense 2 BLE smart irrigation controllers through Home Assistant. It communicates directly with the device over Bluetooth Low Energy using the Nordic UART Service (NUS) — no cloud account, no hub, and no internet connection required.

The integration automatically discovers nearby Aiper devices via BLE advertisements, polls them on an adaptive schedule, and exposes sensors, binary sensors, switches, and services for monitoring and controlling irrigation.

## Supported Devices

| Model Prefix | Description |
|--------------|-------------|
| Aiper-WR-* | IrriSense 2 Wireless Router models |
| Aiper_WR_* | IrriSense 2 (alternate naming) |
| Aiper-IrriSense* | IrriSense branded models |

All devices using the Nordic UART BLE protocol with the Aiper command set are supported. The integration identifies devices by their BLE advertisement name matching the patterns above.

## Installation

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** > **Custom repositories**
3. Add `https://github.com/knobunc/aiper` with category **Integration**
4. Search for "Aiper IrriSense" and install it
5. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/aiper` directory into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup / Installation Parameters

The integration supports two setup methods:

### Automatic Discovery (Recommended)

When an Aiper IrriSense device is within BLE range, Home Assistant will automatically detect it via Bluetooth advertisement. A notification will appear prompting you to set up the device.

1. Click the notification or go to **Settings** > **Devices & Services**
2. The discovered device will appear with its name and BLE address
3. Click **Configure** and confirm the device
4. The integration will test the BLE connection before completing setup
5. If the connection test fails, you will see a "Failed to connect" error — move the device closer or check your Bluetooth adapter

### Manual Setup

If auto-discovery does not find your device:

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Aiper IrriSense"
3. Select your device from the list of discovered Aiper BLE devices
4. Confirm the device to complete setup

If no Aiper devices are found, the setup will abort with "No Aiper IrriSense devices found."

## Configuration Parameters

After setup, you can adjust polling intervals via the integration's options:

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| Idle poll interval | 60 seconds | 30–300 s | How often to poll the device when not irrigating |
| Active poll interval | 15 seconds | 5–60 s | How often to poll during active irrigation |

To change these settings: **Settings** > **Devices & Services** > **Aiper IrriSense** > **Configure**.

## Supported Functions

### Sensors

| Entity | Unit | Description |
|--------|------|-------------|
| Status | — | Current device status: Idle or Irrigating |
| Current Zone | — | Name of the zone being irrigated, or Idle |
| Run Time | minutes | Duration of the current irrigation run |
| Progress | % | Completion percentage of the current irrigation |
| Water Pressure | PSI | Current water pressure reading |
| Firmware | — | Device firmware version (diagnostic) |
| Next Run | timestamp | Next scheduled irrigation time |

### Diagnostic Sensors

These are disabled by default and can be enabled in the entity settings:

| Entity | Unit | Description |
|--------|------|-------------|
| Valve | — | Current valve state value |
| Model | — | Device model identifier |
| Serial Number | — | Device serial number |
| Latitude | — | Installation latitude (set by phone app) |
| Longitude | — | Installation longitude (set by phone app) |

Always enabled diagnostics:

| Entity | Unit | Description |
|--------|------|-------------|
| BLE RSSI | dBm | Bluetooth signal strength |

### Binary Sensors

| Entity | Type | Description |
|--------|------|-------------|
| Irrigating | Running | Whether irrigation is currently active |
| Rain Detected | Moisture | Whether the rain sensor has detected rain |

Diagnostic binary sensors:

| Entity | Type | Description |
|--------|------|-------------|
| Water Flow | Problem | Whether a water flow issue has been detected |
| Connected | Connectivity | Whether the device is reachable via BLE |

### Switches

| Entity | Description |
|--------|-------------|
| Use Rain Sensor | Enable/disable the physical rain sensor |
| Use Rain Forecast | Enable/disable weather-based rain pause |
| Use Wind Forecast | Enable/disable weather-based wind pause |
| All Schedules | Master switch to enable/disable all irrigation plans |
| Plan: *zone* *time* *days* | Per-plan switches (dynamically created as plans are discovered) |

## Data Update Mechanism

The integration uses a **connect-poll-disconnect** pattern over BLE:

1. **Connect** to the device via BLE (Nordic UART Service)
2. **Send commands** to query device state (workInfo, DevInfo, GetSenseSwitch)
3. **Receive responses** and update the coordinator state
4. **Disconnect** from BLE

This pattern ensures the device's BLE connection is not held open, allowing the Aiper phone app to connect between polls.

### Polling Schedule

| State | Interval | Description |
|-------|----------|-------------|
| Idle | 60 seconds | Default polling when not irrigating |
| Irrigating | 15 seconds | Faster polling during active irrigation |
| Unavailable | 120 seconds | Reduced polling when device is unreachable |

### Zone and Plan Discovery

Every 10 minutes (when not irrigating), the integration:
- Queries the device for its zone/map configuration
- Fetches all irrigation plan details
- Retrieves GPS location coordinates
- Dynamically creates switch entities for any new plans

### Unsolicited Notifications

The device proactively sends notifications for:
- **Real-time progress** during irrigation (zone, run time, progress)
- **Abnormal reminders** (rain detected, water shortage)
- **Alarm events** (status changes)

These are processed during each poll cycle to ensure the state stays current between polling intervals.

## Services (Actions)

### aiper.start

Start irrigation on a specific zone.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| device_id | Yes | — | Target device |
| map_id | Yes | — | Zone/map ID to irrigate |
| water_yield | No | 0.25 | Water yield rate (0.1 = low, 0.25 = medium, 0.5 = high) |

### aiper.stop

Stop the current irrigation run.

| Parameter | Required | Description |
|-----------|----------|-------------|
| device_id | Yes | Target device |

### aiper.pause

Pause irrigation (the device treats this the same as stop).

| Parameter | Required | Description |
|-----------|----------|-------------|
| device_id | Yes | Target device |

### aiper.water_area

Irrigate specific zones by segment ID. Useful for watering multiple zones in sequence.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| device_id | Yes | — | Target device |
| segment_ids | Yes | — | Comma-separated zone/map IDs |
| water_yield | No | 0.25 | Water yield rate |
| point_time | No | 1 | Minutes per point (for type 2 maps) |

### aiper.turn_on / aiper.turn_off / aiper.toggle

Enable, disable, or toggle all irrigation schedules at once.

| Parameter | Required | Description |
|-----------|----------|-------------|
| device_id | Yes | Target device |

### aiper.send_command

Send a raw BLE command to the device. For advanced users and debugging.

| Parameter | Required | Description |
|-----------|----------|-------------|
| device_id | Yes | Target device |
| command | Yes | BLE command name (e.g., DevInfo, workInfo) |
| data | No | Optional JSON data for the command |

## Zone Map

The integration provides a rendered image entity (`image.irrisense_zone_map`) that displays your irrigation zones as a map, similar to robot vacuum integrations. The map shows:

- **Zone waypoints** — colored circles connected by lines showing the watering path for each zone
- **Zone labels** — zone names positioned at the centroid of each zone's points
- **Device origin** — a crosshair marker at the controller's (0, 0) position
- **Live sprinkler position** — a red dot showing the current sprinkler location during irrigation
- **Legend** — zone names with their assigned colors

The map updates each poll cycle. During irrigation, the live position dot tracks the sprinkler in real time.

### Map Rotation

The device uses an internal coordinate system that has no inherent compass heading. A **Map Rotation** number entity (`number.irrisense_map_rotation`) lets you set the device's heading angle (0–359°) so the rendered map aligns with north or your preferred orientation. Adjust the slider until the map matches your yard layout.

## Automation Examples

### Stop irrigation when rain is detected

```yaml
automation:
  - alias: "Stop irrigation on rain"
    trigger:
      - platform: state
        entity_id: binary_sensor.irrisense_rain_detected
        to: "on"
    action:
      - service: aiper.stop
        data:
          device_id: !input device_id
```

### Send notification on water flow issue

```yaml
automation:
  - alias: "Alert on water flow problem"
    trigger:
      - platform: state
        entity_id: binary_sensor.irrisense_water_flow
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Irrigation Alert"
          message: "Water flow issue detected on your IrriSense controller."
```

### Disable schedules at night

```yaml
automation:
  - alias: "Disable irrigation schedules overnight"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: aiper.turn_off
        data:
          device_id: !input device_id

  - alias: "Re-enable irrigation schedules in morning"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: aiper.turn_on
        data:
          device_id: !input device_id
```

### Monitor irrigation progress

```yaml
automation:
  - alias: "Notify when irrigation completes"
    trigger:
      - platform: state
        entity_id: binary_sensor.irrisense_irrigating
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Irrigation Complete"
          message: "Your irrigation run has finished."
```

## Use Cases

### Scheduled Irrigation Management

Use the per-plan switch entities to enable or disable individual irrigation schedules directly from the Home Assistant dashboard. The "All Schedules" master switch provides a quick way to pause all irrigation without modifying individual plans.

### Weather-Responsive Irrigation

Enable the "Use Rain Sensor" and "Use Rain Forecast" switches to let the device automatically skip irrigation when rain is detected or forecasted. Combine with Home Assistant weather integrations for more sophisticated rules.

### Water Usage Monitoring

Track the Water Pressure sensor and Water Flow binary sensor to monitor your irrigation system's health. Set up alerts for low pressure or flow anomalies that could indicate leaks or blockages.

### Remote Control

Use the start/stop services in automations or scripts to control irrigation from anywhere through Home Assistant's remote access. Useful for starting a quick watering session while away from home.

## Supported Devices

The integration auto-discovers devices via BLE advertisements matching these patterns:

- `Aiper-WR-*`
- `Aiper_WR_*`
- `Aiper-IrriSense*`

Currently tested with the **Aiper IrriSense 2** irrigation controller. Other Aiper irrigation controllers using the same BLE protocol may also work.

## Known Limitations

- **BLE Range**: Bluetooth Low Energy has a typical range of approximately 30 feet (10 meters). The Home Assistant host must be within BLE range of the IrriSense controller. Walls and other obstacles reduce effective range.

- **Single BLE Connection**: The IrriSense device supports only one BLE connection at a time. During each poll cycle (a few seconds), the Aiper phone app cannot connect. The connect-poll-disconnect pattern minimizes this window.

- **GPS Coordinates**: The device's latitude and longitude are set by the Aiper phone app during initial installation. They cannot be changed through this integration.

- **No Multi-Controller Orchestration**: Each IrriSense device is managed independently. There is no built-in coordination between multiple controllers.

- **Plan Creation**: Irrigation plans (schedules) can only be created and edited through the Aiper phone app. This integration can enable/disable existing plans but cannot create new ones.

- **Firmware Updates**: Firmware updates must be performed through the Aiper phone app. This integration reports the current firmware version but cannot apply updates.

## Troubleshooting

### Device Not Found

- Ensure the IrriSense controller is powered on and within BLE range
- Verify your Home Assistant host has a working Bluetooth adapter
- Check that no other BLE device or app is maintaining a connection to the controller
- Try moving the Home Assistant host closer to the controller

### Connection Timeouts

- The integration retries automatically on connection failures
- After 10 consecutive failures, a reauthentication flow is triggered
- Check the Home Assistant logs for "Device ... is unavailable" messages
- Ensure no other Bluetooth-heavy integrations are monopolizing the adapter

### Reauthentication Prompt

If you see a reauthentication notification, it means the device has been unreachable for an extended period (10+ consecutive poll failures). Confirm the prompt to retry the connection. Common causes:

- Device is out of BLE range
- Device is powered off
- Bluetooth adapter issue on the Home Assistant host

### Entities Show "Unavailable"

When the device is unreachable, all entities will show as unavailable. The integration will continue polling at the unavailable interval (120 seconds) and automatically recover when the device is reachable again. Recovery is logged at INFO level.

### Stale Sensor Values

If sensor values seem stale, check the BLE RSSI sensor. A very low value (below -90 dBm) indicates a weak signal that may cause intermittent data loss. Move the Home Assistant host closer to the controller.

## Removal

To remove the integration:

1. Go to **Settings** > **Devices & Services**
2. Find the **Aiper IrriSense** integration
3. Click the three-dot menu > **Delete**
4. Confirm the removal

This will remove all entities, devices, and configuration associated with the integration. The physical device is not affected and can be re-added at any time.
