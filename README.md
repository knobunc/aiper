# Aiper IrriSense

A [Home Assistant](https://www.home-assistant.io/) custom integration for the [Aiper IrriSense 2](https://www.aiper.com/) BLE smart irrigation controller.

Communicates directly with the device over Bluetooth Low Energy using the Nordic UART Service — no cloud, no hub, fully local.

**Integration Quality Scale: Platinum** — see [quality_scale.yaml](custom_components/aiper/quality_scale.yaml) for details. Full documentation at [docs/integration.md](docs/integration.md).

## Features

- **Sensor entities**: status, current zone, run time, progress, water pressure, firmware version, next scheduled run
- **Diagnostic sensors**: model, serial number, latitude, longitude, BLE RSSI, valve state, water flow, connected
- **Binary sensors**: irrigating, rain detected
- **Switches**:
  - Use Rain Sensor, Use Rain Forecast, Use Wind Forecast (sense settings)
  - Per-plan schedule enable/disable (dynamically created as plans are added)
  - All Schedules master switch
- **Zone map**: rendered image entity showing irrigation zones, waypoints, and live sprinkler position
- **Map rotation**: number entity to align the device's coordinate system with compass north
- **Services**: start/stop/pause irrigation, water specific zones, enable/disable schedules, send raw BLE commands
- **Auto-discovery** via BLE advertisement matching
- **Connect-poll-disconnect** pattern — does not block the Aiper phone app
- **Adaptive polling**: 15s when irrigating, 60s when idle

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** → **Custom repositories**
3. Add `https://github.com/knobunc/aiper` with category **Integration**
4. Search for "Aiper IrriSense" and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/aiper` directory into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

The integration auto-discovers Aiper IrriSense devices via BLE. Once discovered, confirm the device in the Home Assistant notifications or go to **Settings** → **Devices & Services** → **Add Integration** → **Aiper IrriSense**.

### Options

- **Idle poll interval** (default 60s): how often to poll when not irrigating
- **Active poll interval** (default 15s): how often to poll during irrigation

## Services

| Service | Description |
|---------|-------------|
| `aiper.start` | Start irrigation on a specific zone |
| `aiper.stop` | Stop current irrigation |
| `aiper.pause` | Pause irrigation (device treats as stop) |
| `aiper.water_area` | Irrigate specific zones by segment ID |
| `aiper.turn_on` | Enable all schedules |
| `aiper.turn_off` | Disable all schedules |
| `aiper.toggle` | Toggle all schedules |
| `aiper.send_command` | Send a raw BLE command to the device |

## Requirements

- Home Assistant 2024.1.0 or later
- Bluetooth adapter accessible to Home Assistant
- Aiper IrriSense 2 irrigation controller within BLE range
