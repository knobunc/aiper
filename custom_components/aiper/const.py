"""Constants for the Aiper IrriSense integration."""

from homeassistant.const import Platform

DOMAIN = "aiper"
MANUFACTURER = "Aiper"

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.IMAGE,
]

# Nordic UART Service UUIDs
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

XOR_KEY = bytes([0x12, 0x34, 0x56, 0x78])
MAX_CHUNK = 152

# Adaptive polling intervals (seconds)
POLL_IDLE = 60
POLL_IRRIGATING = 15
POLL_UNAVAILABLE = 120

COMMAND_TIMEOUT = 10.0

UNSOLICITED_TYPES = frozenset({"realTimeProgress", "AbnormalReminder", "Alarm"})

# SetSenseSwitch type values
SENSE_TYPE_WEATHER_RAIN = 0
SENSE_TYPE_WEATHER_WIND = 1
SENSE_TYPE_RAIN_SENSOR = 2

# Zone/plan discovery interval (seconds)
ZONE_DISCOVERY_INTERVAL = 600

# Config entry data keys
CONF_ADDRESS = "address"
CONF_SERIAL = "serial"
CONF_MODEL = "model"

# Options keys
CONF_IDLE_POLL_INTERVAL = "idle_poll_interval"
CONF_ACTIVE_POLL_INTERVAL = "active_poll_interval"
