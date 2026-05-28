# Aiper Pool Robot BLE API Specification

**Reverse-engineered from:** Aiper Android App v3.3.2 (com.aiper.link)
**Date:** 2026-05-28
**Purpose:** Reference for Home Assistant integration via BLE proxies

---

## Table of Contents

1. [Overview](#1-overview)
2. [BLE Scanning & Discovery](#2-ble-scanning--discovery)
3. [Device Types & BLE UUIDs](#3-device-types--ble-uuids)
4. [Connection Establishment](#4-connection-establishment)
5. [Encryption Protocols](#5-encryption-protocols)
6. [Message Framing](#6-message-framing)
7. [Command Format](#7-command-format)
8. [Available Commands](#8-available-commands)
9. [Device State (Shadow Model)](#9-device-state-shadow-model)
10. [WiFi Provisioning over BLE](#10-wifi-provisioning-over-ble)
11. [Cloud Transport (MQTT & REST)](#11-cloud-transport-mqtt--rest)
12. [Home Assistant Integration Notes](#12-home-assistant-integration-notes)

---

## 1. Overview

Aiper pool robots expose a BLE GATT interface that supports the **same JSON command protocol** used over MQTT, but with a different transport encoding. This means nearly all device operations available through the cloud can also be performed locally over BLE.

```
HA Bluetooth Proxy  <--BLE-->  Aiper Pool Robot
     |
     v
  BLE GATT write/notify on a single service
     |
     v
  JSON commands (XOR or ECDH encrypted, Base64 encoded)
```

Key facts:
- BLE uses a single GATT service with write and notify characteristics (often the same UUID)
- Commands are JSON, encrypted, Base64-encoded, and newline-terminated
- Two encryption modes: XOR (legacy) and ECDH-secp256r1 (newer devices)
- The app uses Nordic Semiconductor's BLE library internally

---

## 2. BLE Scanning & Discovery

### Advertisement Name Format

Aiper devices advertise with names matching the pattern:

```
Aiper-<MODEL>-<SUFFIX>
Aiper_<MODEL>_<SUFFIX>
```

Examples: `Aiper-X9-A1B2C3`, `Aiper_S1_D4E5F6`

The app filters for device names starting with `"Aiper"` (case-sensitive).

### Device Type Identification from BLE Name

The model segment (second field when split on `-` or `_`) is matched against known model strings to determine the `DeviceType`:

```python
name = "Aiper-X9-A1B2C3"
delimiter = "_" if "_" in name else "-" if "-" in name else ""
parts = name.split(delimiter)
model = parts[1] if len(parts) > 2 else ""
# model = "X9" -> DeviceType.X9
```

### New Protocol Detection

During scanning, the app checks BLE manufacturer-specific data to determine if a device uses the newer ECDH encryption:

```
ScanRecord.manufacturerSpecificData[companyId=0]
  -> if first byte == 0x01: device uses ECDH protocol
  -> otherwise: device uses XOR protocol
```

This flag is stored per-connection and determines the encryption mode.

### Scan Parameters

| Parameter | Value |
|-----------|-------|
| Scan mode | `SCAN_MODE_OPPORTUNISTIC` (0) |
| Scan filter | None (empty filter list) |
| Auto-stop timeout | 30,000 ms |
| Name prefix filter | `"Aiper"` (in scan callback) |

---

## 3. Device Types & BLE UUIDs

### Group 1: Standard Protocol (most devices)

```
Service:  4a5ad444-2537-11ee-be56-0242ac120002
Write:    4a5a54e6-2537-11ee-be56-0242ac120002
Notify:   4a5a54e6-2537-11ee-be56-0242ac120002  (same as write)
```

| DeviceType | Models | SN Prefixes |
|------------|--------|-------------|
| S1 | Surfer S1, Surfer M1, EcoSurfer S1, EcoSurfer M1 | S1, M1, 1S, 1M |
| S2 | Surfer S2, Surfer M2, EcoSurfer S2/M2/W2/P1 | S2, M2, 2S, SM, SW, SP |
| ScubaN30 | Scuba S3 | NL, N0, N6 |
| ScubaN31 | Scuba V3, Scuba N31, Scuba N3 | N1, N2, N3 |
| SurferB30 | Surfer B30, EcoSurfer Senti | B3 |
| W2 | HydroComm, HydroComm Pro/Pure, HydroHub | W2, WP, WE |
| ScubaX1 | Scuba X1, Scuba N1 Max | T1, TM |
| X5ProMax | Scuba N1 2025, Scuba N1 Plus, Scuba S1 2025, Scuba N1, Scuba S1 | 51, 53, 52, X5, XS |
| X6 | Scuba S1 Pro, Scuba N1 Pro/Ultra, Scuba P1 Pro/Ultra | X6, XN, XU, 6P, 7P |

### Group 2: New Protocol (X9 Series)

```
Service:  10101910-0000-1000-8000-00805f9b34fb
Write:    9884d812-1810-4a24-94d3-b2c11a851fac
Notify:   dfd4416e-1810-47f7-8248-eb8be3dc47f9
```

| DeviceType | Models | SN Prefixes |
|------------|--------|-------------|
| X9 | Scuba X1 Pro Max | X9 |
| ScubaX1Pro | Scuba X1 Pro | TX |
| X30 | Scuba V3 Ultra | X0 |
| X30SE | Scuba V3 Pro | XE |

### Group 3: Nordic UART Service (Irrigation devices)

```
Service:  6e400001-b5a3-f393-e0a9-e50e24dcca9e
Write:    6e400002-b5a3-f393-e0a9-e50e24dcca9e  (NUS RX)
Notify:   6e400003-b5a3-f393-e0a9-e50e24dcca9e  (NUS TX)
```

| DeviceType | Models | SN Prefixes |
|------------|--------|-------------|
| WR | IrriSense WR, Irrigo WR, IrriSense 2/N2/II | WR, WG, WC |
| IrriSenseSE | IrriSense 2 SE | WL |

### Group 4: Pooljoy (unique notify UUID)

```
Service:  4a5ad444-2537-11ee-be56-0242ac120002
Write:    4a5a54e6-2537-11ee-be56-0242ac120002
Notify:   4b5a54e6-2537-11ee-be56-0242ac120002  (note: 4b, not 4a)
```

| DeviceType | Models | SN Prefixes |
|------------|--------|-------------|
| Pooljoy | BS270 | AA |

### Group 5: ScubaT30 (anomalous - all same UUID)

```
Service:  4a5ad444-2537-11ee-be56-0242ac120002
Write:    4a5ad444-2537-11ee-be56-0242ac120002  (same as service)
Notify:   4a5ad444-2537-11ee-be56-0242ac120002  (same as service)
```

| DeviceType | Models | SN Prefixes |
|------------|--------|-------------|
| ScubaT30 | Scuba T30 | T3 |

### Series Groupings

- **X9Series:** X9, ScubaX1Pro, WR, X30, X30SE, IrriSenseSE
- **Surfers:** S1, S2, SurferB30
- **IrriSenses:** WR, IrriSenseSE (use NUS UUIDs, smaller chunk size)

---

## 4. Connection Establishment

### Connection Flow

1. Scan for BLE devices with name starting with `"Aiper"`
2. Parse model from BLE name to determine `DeviceType` and UUIDs
3. Check manufacturer data for new protocol flag
4. Connect to the device (timeout: 10s constant, 3s default in practice)
5. Discover GATT services and locate the service/write/notify characteristics
6. Request MTU (512 preferred, 300 fallback)
7. Enable notifications on the notify characteristic
8. If new protocol detected, perform ECDH key exchange
9. Device is ready for commands

### Connection Parameters

| Parameter | Value |
|-----------|-------|
| MTU request (primary) | 512 |
| MTU request (fallback) | 300 |
| Connection timeout | 10,000 ms (constant), 3,000 ms (default) |
| Write timeout | 5,000 ms per chunk |
| Send/command timeout | 3,000 ms |
| Write mutex timeout | 5,000 ms |
| Write type | WRITE_TYPE_NO_RESPONSE (1) in BleProcessor |

### GATT Service Discovery

```python
service = gatt.getService(UUID(device_type.service_uuid))
write_char = service.getCharacteristic(UUID(device_type.write_uuid))
notify_char = service.getCharacteristic(UUID(device_type.notify_uuid))
# Enable notifications on notify_char
# For most devices, write_char and notify_char are the same characteristic
```

---

## 5. Encryption Protocols

### XOR Protocol (Legacy - Default)

Used by most devices unless manufacturer data indicates otherwise.

**Key:** `[0x12, 0x34, 0x56, 0x78]` (4 bytes, repeating)

**Encryption:**
```python
def xor_encrypt(plaintext_bytes, key=[0x12, 0x34, 0x56, 0x78]):
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(plaintext_bytes)])
```

**Full encode (for sending):**
```python
json_str = '{"type":"DevInfo","data":{},"chksum":12345}'
encrypted = xor_encrypt(json_str.encode('utf-8'))
message = base64.b64encode(encrypted).decode('ascii') + "\n"
# Write message.encode('utf-8') to BLE characteristic
```

**Full decode (for receiving):**
```python
# Accumulate notification data until "\n" is received
raw = base64.b64decode(accumulated_base64)
decrypted = xor_encrypt(raw)  # XOR is symmetric
json_str = decrypted.decode('utf-8')
response = json.loads(json_str)
```

### ECDH-secp256r1 Protocol (New)

Used by devices whose BLE advertisement has manufacturer data byte 0 == 0x01 at company ID 0.

**Key Exchange:**
1. Generate a local secp256r1 (P-256) key pair
2. Export local public key as uncompressed point (65 bytes: `0x04 || X[32] || Y[32]`)
3. Send public key to device via BLE command
4. Receive device's public key (65 bytes, same format)
5. Perform ECDH key agreement
6. Take first 16 bytes of shared secret as AES-128 key

**Encryption:**
```python
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

def ecdh_encrypt(plaintext_bytes, shared_key_16):
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext_bytes) + padder.finalize()
    cipher = Cipher(algorithms.AES(shared_key_16), modes.CBC(iv))
    encrypted = cipher.encryptor().update(padded) + cipher.encryptor().finalize()
    return base64.b64encode(iv + encrypted).decode('ascii') + "\n"

def ecdh_decrypt(base64_data, shared_key_16):
    raw = base64.b64decode(base64_data)
    iv = raw[:16]
    ciphertext = raw[16:]
    cipher = Cipher(algorithms.AES(shared_key_16), modes.CBC(iv))
    padded = cipher.decryptor().update(ciphertext) + cipher.decryptor().finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()
```

**Key implementation files:**
- `EcdhP256Util.java` - Key pair generation, point export/import, shared secret derivation
- `EncryptProtocol.java` - `XOR` and `EcdhSecp256r1` sealed subclasses
- `CmdFactory.java` - Encryption/decryption dispatch (lines 187-203)

---

## 6. Message Framing

### Outbound (App -> Device)

1. Build JSON command string
2. Encrypt (XOR or ECDH depending on protocol)
3. Base64-encode the encrypted bytes
4. Append `"\n"` as message terminator
5. Split into chunks of max 200 bytes (152 for irrigation devices)
6. Write each chunk sequentially to the write characteristic

```
JSON string
  -> encrypt(json.encode('utf-8'))
  -> base64encode(encrypted)
  -> append "\n"
  -> split into 200-byte chunks
  -> write each chunk to GATT characteristic
```

### Inbound (Device -> App)

1. Receive BLE notification data
2. Decode as UTF-8 string
3. Append to buffer
4. If buffer ends with `"\n"`:
   - Strip the newline
   - Base64-decode the complete buffer
   - Decrypt (XOR or ECDH)
   - Parse as JSON
   - Clear buffer
5. If buffer does not end with `"\n"`, wait for more data

```
BLE notification bytes
  -> decode as UTF-8
  -> append to StringBuffer
  -> if ends with "\n":
       base64decode(buffer)
       -> decrypt(decoded)
       -> json.loads(decrypted)
       -> clear buffer
  -> else: wait for next notification
```

### Chunking Constants

| Parameter | Value |
|-----------|-------|
| Max chunk size (general) | 200 bytes |
| Max chunk size (irrigation) | 152 bytes |
| Message terminator | `"\n"` (newline, 0x0A) |
| Retry on error code -3 | After 200ms delay |

---

## 7. Command Format

### Standard Devices (Non-X9 Series)

```json
{
  "type": "<CommandType>",
  "data": { ... },
  "chksum": <crc16_modbus_of_data_json>
}
```

### X9 Series Devices

```json
{
  "<CommandType>": { ... },
  "chksum": <crc16_modbus_of_data_json>
}
```

### CRC16-Modbus Checksum

- Algorithm: CRC16-Modbus
- Initial value: 39270 (0x9996)
- Input: UTF-8 bytes of the JSON-serialized `data` field only (not the full command)
- The `chksum` field is added to the command map before encryption
- IrriSense devices skip the checksum

### Response Format

```json
{
  "type": "<CommandType>",
  "data": { ... }
}
```

For X9 series:
```json
{
  "<CommandType>": { ... }
}
```

Responses are matched to requests by the `type` field (case-insensitive comparison).

---

## 8. Available Commands

### Core Status Commands

These commands work over BLE, TCP, and MQTT:

| Command Type | Direction | Description |
|-------------|-----------|-------------|
| `DevInfo` | Query/Subscribe | Device information (model, firmware, serial) |
| `OpInfo` | Query (once) | Operational info, online status |
| `NetStat` | Subscribe | Network/connectivity status |
| `FactoryRestore` | Set | Reset device to factory defaults |

### Device Control Commands

These are the primary commands for controlling the pool robot:

**Cleaning Operations:**

| Command Type | Direction | Parameters | Description |
|-------------|-----------|------------|-------------|
| `FastTask` | Set | | Start immediate cleaning |
| `StartTask` | Set | | Start scheduled cleaning task |
| `StopTask` | Set | | Stop current cleaning |
| `WeekdayTask` | Set | schedule data | Set weekday-based schedule |
| `IntervalTask` | Set | interval data | Set interval-based schedule |
| `CreateScheduledTask` | Set | task config | Create a new scheduled task |
| `DeleteScheduledTask` | Set | task id | Delete a scheduled task |

**Cleaning Mode & Path:**

| Command Type | Direction | Parameters | Description |
|-------------|-----------|------------|-------------|
| `SetBottomRunMode` | Set | `mode` | Set bottom cleaning mode |
| `GetBottomRunMode` | Query | | Get current bottom cleaning mode |
| `SetEntryPoint` | Set | `type` | Set entry/exit point |
| `GetEntryPoint` | Query | | Get current entry point |
| `SetMultiBottom` | Set | zone config | Multi-zone bottom cleaning |
| `SetSurfaceWater` | Set | `workTime`, `distanceSide`, `circleCount`, `lineCount` | Surface cleaning config |
| `GetSurfaceWater` | Query | | Get surface cleaning config |
| `GetWorkMode` | Query | | Get current work mode |
| `GetWorkModeReport` | Subscribe | | Work mode change reports |

**Speed & Motor:**

| Command Type | Direction | Parameters | Description |
|-------------|-----------|------------|-------------|
| `SetSpeed` | Set | `lineSpeed`, `angularSpeed`, `pumpSpeedSec` | Set movement speeds |
| `SetMotorThreshold` | Set | `driveMotor`, `pumpMotor`, `turnMotor`, `airMotor`, `pulsatorMotor` | Motor thresholds |

**Device Features:**

| Command Type | Direction | Parameters | Description |
|-------------|-----------|------------|-------------|
| `SetLightInfo` | Set | light config | Control robot lights |
| `GetLightInfo` | Query | | Get light status |
| `SetFountainInfo` | Set | fountain config | Control fountain |
| `GetFountainInfo` | Query | | Get fountain status |
| `SetVoiceBroadcast` | Set | | Voice announcements |
| `SetSpeakerState` | Set | state | Speaker on/off |
| `GetSpeakerState` | Query | | Get speaker status |
| `SetVolumeType` | Set | `mode`, `volumeArr` | Audio volume/EQ |
| `GetVolumeType` | Query | | Get volume settings |
| `SetSuperEco` | Set | | Enable/disable eco mode |
| `SetAutoWork` | Set | | Auto-work settings |

**Status Queries:**

| Command Type | Direction | Description |
|-------------|-----------|-------------|
| `GetAlarm` | Query | Alarm/error information |
| `GetRubbishBoxStatus` | Query | Trash/debris box status |
| `Inwater` | Query | Is robot in water? |

**Advanced:**

| Command Type | Direction | Description |
|-------------|-----------|-------------|
| `ManualTest` | Set | Manual test mode (`entry`, `cleanMode`) |
| `SetInspectionSetting` | Set | Inspection parameters |
| `SetAutomationTaskSetting` | Set | Automation task config |
| `SetMachineSetting` | Set | Machine settings backup/restore |
| `SetAdjustButton` | Set | Button behavior config |
| `TimeZoneSet` | Set | Set device timezone |

### BLE-Only Commands (WiFi Provisioning)

| Command Type | Direction | Description |
|-------------|-----------|-------------|
| `NetConfig` | Set | Send WiFi credentials (AES encrypted) |
| `RootCert` | Set | Send AWS root CA certificate |
| `ThingCert` | Set | Send AWS thing certificate |
| `CertSecret` | Set | Send AWS IoT endpoint and private key |

### Subscribe/Report Commands

These provide continuous state updates:

| Command Type | Description |
|-------------|-------------|
| `OpInfoReport` | Operational info updates |
| `GetWorkModeReport` | Work mode changes |
| `GetRubbishBoxStatusReport` | Trash status updates |
| `InwaterReport` | In-water status changes |
| `SuperEcoReport` | Eco mode status |
| `MotorThresholdReport` | Motor status updates |
| `SpeedReport` | Speed/velocity updates |
| `AutomationTaskReport` | Automation task status |
| `FinishTaskReport` | Task completion notification |

### AT Commands

Some devices (particularly W2/HydroComm series) support AT-style commands:

**Query AT:** `sendQueryAT(name, cmd, sn)` - queries device state
**Set AT:** `sendSetAT(name, cmd)` - sets device parameters

AT command responses are prefixed with `"+ok"` or `"+<atName>:"`.

---

## 9. Device State (Shadow Model)

The device reports its state through the Shadow model, which contains ~43 sub-models. Key fields relevant to HA integration:

### Machine State

| Field | Type | Description |
|-------|------|-------------|
| `cap` | int | Battery capacity/percentage |
| `mode` | int | Current operating mode |
| `status` | int | Current robot status |
| `temp` | float | Temperature reading |
| `warn` | int | Warning flags |
| `warn_code` | string | Warning code details |
| `in_water` | bool | Whether robot is in water |
| `link` | int | Link/connectivity status |
| `light` | int | Light on/off status |
| `solar_status` | int | Solar panel status |
| `visual` | int | Visual/camera status |

### Network State

| Field | Type | Description |
|-------|------|-------------|
| `online` | bool | Device online status |
| `rssi` | int | WiFi signal strength |

### Operational Info

| Field | Type | Description |
|-------|------|-------------|
| `wifi_ssid` | string | Connected WiFi network |
| `firmware_version` | string | Current firmware |
| `model` | string | Device model identifier |

---

## 10. WiFi Provisioning over BLE

This section documents how the app provisions WiFi credentials to a device over BLE. Useful if the HA integration needs to set up new devices.

### WiFi Config Data Format

```json
{
  "mode": <int>,
  "ssid": "<hex-encoded AES-encrypted SSID>",
  "passwd": "<hex-encoded AES-encrypted password>",
  "id": "<hex-encoded 16-byte random IV>",
  "aeskey": "<HTTP AES key as string>",
  "aesiv": "<HTTP AES IV as string>",
  "encryptkey": "<HTTP encrypt key>",
  "token": "<user login token>",
  "url": "<SERVICE_ADDRESS>/equipment/registerEquipmentToAWS",
  "timestamp": "<current_time_millis>",
  "randdata": "<random 0-9999>"
}
```

### WiFi Credential Encryption

- Algorithm: AES/CBC/ZeroBytePadding
- Key: Static AES key `[0x02, 0x46, 0xB9, 0xC0, 0x0A, 0xF1, 0xEE, 0x10, 0xFA, 0x0C, 0xD0, 0x0D, 0x48, 0x00, 0xD7, 0x20]`
- IV: Random 16 bytes (sent as `id` field)
- SSID and password are each AES-encrypted separately, then hex-encoded

### Provisioning Flow

1. Connect to device over BLE
2. Subscribe to `NetConfigFail` (X9 series) or `NetConfigProgress` responses
3. Send WiFi config as `NetConfig` command
4. Monitor progress/failure (error codes 3000-3999 = WiFi failures)
5. Once WiFi connects, the device registers itself with Aiper's AWS backend
6. For HydroComm devices, send an `Activate` command with timestamps

---

## 11. Cloud Transport (MQTT & REST)

The Aiper app communicates with devices through three transports, selectable via `CmdLinkType`: `BLUETOOTH`, `TCP`, and `MQTT`. The same JSON command protocol (XOR-encrypted, Base64-encoded) is used across all transports.

### MQTT via AWS IoT Core

The primary cloud transport. Commands sent over MQTT use the exact same encryption and JSON format as BLE.

#### MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `aiper/things/{sn}/downChan` | App → Device | Command channel (publish) |
| `aiper/things/{sn}/upChan` | Device → App | Response channel (subscribe) |
| `aiper/things/{sn}/app/report` | Device → App | X9 Series status reports |
| `aiper/things/{sn}/shadow/report` | Device → App | Non-X9 status reports |
| `$aws/things/{sn}/shadow/get/accepted` | AWS → App | Shadow query response |
| `$aws/things/{sn}/shadow/update` | App → AWS | Shadow state update |
| `$aws/things/{sn}/shadow/update/accepted` | AWS → App | Shadow update confirmation |

`{sn}` is the device serial number.

#### Authentication Flow

1. App authenticates to Aiper REST API (email/password → JWT token)
2. App calls `api.getOpenIdToken()` to get AWS credentials:
   - `identityId` — Cognito Identity ID (also used as MQTT client ID)
   - `identityPoolId` — Cognito Identity Pool ID
   - `token` — OpenID Connect token
   - `iotEndpoint` — AWS IoT Core endpoint (`{account-id}.iot.{region}.amazonaws.com`)
   - `region` — AWS region
3. App creates `CognitoCachingCredentialsProvider` with `DeveloperProvider`
4. App connects `AWSIotMqttManager(clientId=identityId, endpoint=iotEndpoint)` with Cognito credentials
5. MQTT connection uses AWS SigV4 authentication

#### Multi-Session Limitation

**The MQTT client ID is the Cognito Identity ID (per-user).** AWS IoT Core only allows one connection per client ID (MQTT 3.1.1 spec). A second connection from the same user account will disconnect the first.

This means a Home Assistant integration using MQTT cannot coexist with the official Aiper app on the same user account. Workarounds:
- Use a separate Aiper account and share the device to it (if supported)
- Use BLE transport instead (no concurrency conflict)

#### MQTT Connection Parameters

| Parameter | Value |
|-----------|-------|
| Keep-alive | 60 seconds |
| Reconnect retry limits | 5 attempts |
| Max auto-reconnect | Unlimited (-1) |
| QoS | Standard MQTT QoS levels |

### REST API

The app uses a Retrofit 2 REST API for account management, device registration, and metadata. The base URL is dynamically configured via `BaseConstant.SERVICE_ADDRESS`.

#### Known Base URLs

| Environment | URL |
|-------------|-----|
| Production (Global) | `https://policy.aiper.com/` |
| Production (China) | `https://policy.aiper.com.cn/` |
| Test | `https://bg-test.aipervip.com/` |
| Dev | `https://admin.aipervip.com:30080/` |

#### Key REST Endpoints

**Authentication:**
- `checkEmail` — Check if email is registered
- `sendEmail` / `sendEmailExpire` — Send verification email
- `registerByCode` — Register new account
- `forgetPwd` — Password reset
- `users/current` — Get current user
- `users/token/refresh` — Refresh JWT token

**Device Management:**
- `equipment/existEquipment` — Check if device exists
- `equipment/registerEquipmentToAWS` — Register device to AWS IoT
- `equipment/insertEquipment` — Add device to account
- `equipment/getEquipment` — List user's devices
- `equipment/setName` — Rename device
- `equipment/checkEquipmentOnlineStatus` — Check device online status

**Device Models:**
- `equipmentModel/getList` — Get equipment model list
- `equipmentModel/getAll` — Get all models

**OTA / Support:**
- `support/v1/checkAppVersion` — Check for app updates
- `support/v1/productVerification` — Verify product authenticity
- `support/v1/queryWarrantyPeriod` — Warranty info

**IrriSense Irrigation Records (WrApiService):**
- `wr/wateringRecordStatisticsV2` — Summary stats: total run count, total gallons, water savings
- `wr/getWateringRecordHistoryDataV2` — Paginated history: area, duration, water consumption per run
- `wr/batchWateringRecordReportV2` — Upload device-synced records to cloud

#### REST Authentication

- Token-based: JWT via `users/token/refresh`
- HTTP interceptors inject auth headers on all requests
- 30-second connect/read timeouts

### Local HTTP (Limited)

A local HTTP endpoint exists at `http://192.168.4.1:8001/GetCleanRecord` — this is the device's AP-mode address (used during WiFi setup). Not useful for normal operation.

---

## 12. Home Assistant Integration Notes

### Feasibility Assessment

BLE control via HA Bluetooth proxies is **highly viable**. The protocol is straightforward:
- Well-defined GATT service/characteristic UUIDs per device type
- Simple XOR encryption for legacy devices
- Standard ECDH + AES for newer devices
- JSON command format identical to cloud API
- Newline-delimited message framing

### Recommended HA Entity Mapping

| HA Entity | Source |
|-----------|--------|
| `vacuum` | `FastTask`/`StopTask` for start/stop, `SetBottomRunMode` for mode |
| `sensor.battery` | Shadow `Machine.cap` via `DevInfo` subscribe |
| `sensor.status` | Shadow `Machine.status` via `DevInfo` subscribe |
| `binary_sensor.in_water` | Shadow `Machine.in_water` or `Inwater` query |
| `switch.light` | `SetLightInfo`/`GetLightInfo` |
| `switch.fountain` | `SetFountainInfo`/`GetFountainInfo` |
| `switch.eco_mode` | `SetSuperEco`/`SuperEcoReport` |
| `sensor.temperature` | Shadow `Machine.temp` |
| `sensor.wifi_rssi` | Shadow `NetStat` |

### Implementation Approach

1. **Discovery:** Scan for BLE devices with name prefix `"Aiper"`. Parse model from name.
2. **Device type:** Map model string to UUID group and protocol variant.
3. **Connect:** Standard BLE GATT connection, request MTU 512, discover service.
4. **Encryption setup:**
   - Check manufacturer data for new protocol flag
   - If legacy: use XOR key `[0x12, 0x34, 0x56, 0x78]`
   - If new: perform ECDH handshake, derive AES key
5. **Enable notifications** on notify characteristic.
6. **Send commands:** JSON -> encrypt -> Base64 -> append `\n` -> chunk into 200 bytes -> write.
7. **Receive responses:** Buffer notifications until `\n` -> Base64 decode -> decrypt -> parse JSON.
8. **Polling:** Send `DevInfo` as a subscription to get periodic state updates.

### Key Differences from Cloud API

| Aspect | Cloud (MQTT) | BLE |
|--------|-------------|-----|
| Command JSON | Raw plaintext | XOR or ECDH encrypted |
| Encoding | None | Base64 |
| Framing | MQTT message boundaries | `\n` terminated |
| Chunking | N/A | 200-byte max per write |
| Authentication | AWS IoT credentials | None (proximity = auth) |
| Availability | Requires internet | Local only |
| Latency | ~200-500ms | ~50-100ms |

### Caveats

- **BLE range:** Requires a Bluetooth proxy within range (~10m typical)
- **Single connection:** BLE devices typically only accept one connection at a time. If the Aiper app is connected, HA cannot connect simultaneously.
- **ECDH handshake:** Newer devices (X9, X30, ScubaX1Pro, X30SE) require the ECDH key exchange before commands work. The exact BLE command type for sending the public key needs to be determined empirically.
- **ScubaT30 anomaly:** All three UUIDs point to the service UUID, which is unusual. May need special handling.
- **CRC validation:** Devices may reject commands without a valid CRC16-Modbus checksum.
- **IrriSense devices:** Use Nordic UART Service UUIDs and smaller chunk size (152 bytes). Skip CRC.
- **State subscriptions:** Use `sendAndSubscribe` pattern for continuous state updates rather than polling.

### Example: Start Cleaning (Python pseudocode)

```python
import base64
import json
import struct

XOR_KEY = bytes([0x12, 0x34, 0x56, 0x78])

def crc16_modbus(data: bytes, init=39270) -> int:
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

def xor_encrypt(data: bytes) -> bytes:
    return bytes([b ^ XOR_KEY[i % 4] for i, b in enumerate(data)])

def build_command(cmd_type: str, data: dict = None, x9_series: bool = False) -> bytes:
    if x9_series:
        cmd = {cmd_type: data or {}}
    else:
        cmd = {"type": cmd_type, "data": data or {}}

    if data:
        data_json = json.dumps(data, separators=(',', ':'))
        chksum = crc16_modbus(data_json.encode('utf-8'))
        cmd["chksum"] = chksum

    json_bytes = json.dumps(cmd, separators=(',', ':')).encode('utf-8')
    encrypted = xor_encrypt(json_bytes)
    encoded = base64.b64encode(encrypted).decode('ascii') + "\n"
    return encoded.encode('utf-8')

# Start cleaning
message = build_command("FastTask")
# Split into 200-byte chunks and write to BLE characteristic
for i in range(0, len(message), 200):
    chunk = message[i:i+200]
    await ble_client.write_gatt_char(WRITE_UUID, chunk)
```
