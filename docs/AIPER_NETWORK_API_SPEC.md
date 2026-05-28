# Aiper Pool Robot Network API Specification

**Reverse-engineered from:** Aiper Android App v3.3.2 (com.aiper.link)
**Date:** 2026-05-28
**Purpose:** Reference for Home Assistant integration development

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Regional API Servers](#2-regional-api-servers)
3. [HTTP Transport Layer](#3-http-transport-layer)
4. [Authentication Flow](#4-authentication-flow)
5. [REST API Endpoints](#5-rest-api-endpoints)
6. [AWS IoT MQTT Layer](#6-aws-iot-mqtt-layer)
7. [Device Shadow Model](#7-device-shadow-model)
8. [Command Protocol](#8-command-protocol)
9. [Device Types & Serial Number Prefixes](#9-device-types--serial-number-prefixes)
10. [Local Device API](#10-local-device-api)
11. [Home Assistant Integration Notes](#11-home-assistant-integration-notes)

---

## 1. Architecture Overview

The Aiper ecosystem uses a three-tier architecture:

```
Mobile App  <---REST/HTTPS--->  Aiper Cloud API  <---AWS IoT--->  Device
    |                                |
    +--------AWS IoT MQTT-----------+
    |
    +--------BLE (local)---------> Device (direct, no cloud)
```

- **Cloud REST API**: User auth, device registration, clean records, OTA, scheduling
- **AWS IoT Core MQTT**: Real-time device control and state via Device Shadows
- **BLE**: Direct local control (not covered here, requires physical proximity)
- **Local WiFi AP**: Device exposes `192.168.4.1:8001` when in AP mode

The app is built with Kotlin, uses Retrofit for HTTP, and the AWS IoT Android SDK for MQTT.

---

## 2. Regional API Servers

The base URL is selected per-user based on their registered country. The `domain` field from login response can override this.

| Region | Base URL |
|--------|----------|
| Americas (US, CA, MX, BR, etc.) | `https://apiamerica.aiper.com/` |
| Europe (DE, FR, UK, IT, ES, etc.) | `https://apieurope.aiper.com/` |
| Asia-Pacific (AU, JP, KR, etc.) | `https://apiasia.aiper.com/` |

**Test/Dev environments** (not for production use):
- Test: `https://bg-test.aipervip.com/`
- Dev: `https://admin.aipervip.com:30080/`

**Event tracking** (telemetry, not needed for HA):
- `https://event-tracking.aiper.com/app-new/log`

---

## 3. HTTP Transport Layer

### 3.1 Standard Headers

Every request includes these headers:

| Header | Value | Description |
|--------|-------|-------------|
| `Content-Type` | `application/json` | Always JSON |
| `version` | `3.3.2` | App version string |
| `os` | `android` | Platform identifier |
| `charset` | `UTF-8` | Character encoding |
| `Accept-Language` | `en` / `zh` / etc. | User's language |
| `zoneId` | `America/New_York` etc. | User's timezone ID |
| `token` | `<auth_token>` | Login token (empty string if not logged in) |
| `encryptKey` | `<RSA_encrypted_AES_key>` | Session encryption key (see 3.2) |

### 3.2 Request/Response Encryption

**All POST requests are encrypted.** The app uses a session-based AES encryption scheme:

**Key setup (once per session):**
1. Generate random 16-byte AES key and 16-byte IV (ASCII range 40-126)
2. Package as JSON: `{"key": "<aes_key>", "iv": "<iv>"}`
3. RSA-encrypt with server's public key
4. Send as `encryptKey` header on every request

**RSA Public Keys (Base64-encoded):**
- **International (1024-bit):** `MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCIKoKPqwq1f60hm/2lpHDF/DT4J9YaptuTq78nsxdgnSBAvkIZ3E8dqbEBT/VETjJ9Yr28QtHX13E8QGByYxLzYPldHNXChgOWfSemTEC3TxPvlaSuM9eFUuhqSeGbgoKG7JJNlgjvsPO2cHEhPXJE4qWtKEZVOZBxEeCgAaLZxwIDAQAB`
- **Chinese (2048-bit):** `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAt589p8rBP5tTCv2/mKF36yvIp2adSchprw+0FQOjF6SNwCNyQsqMXiJ1dmAQlIPX8k34OEPNek5jUk99+SrX77JWYCpj4b//TGZE0eeVQGYFZdCX44Un/xKJeEfJV7cZdGnlFN/1up/ujE8Pz8DDc45SnINHs0LmiAHnnZGKzg78FSFIQktiVGHFopQox4w+eSAVnoZVYxTsM0IqSUfkObRGvjf+8AvE8ylx3+t4GmmwvFzh0iCyV+wJuPGkyEyr9AndSm+2pqtga7lq2a/MZWJhAtyqkZSSCOHOzCSuqeFaR7hikwswRza1UVQih6m6rzsbcyhXgyr1sY2ICabE1wIDAQAB`

**Request encryption:**
1. Parse request body as JSON
2. Add `"nonce"` (4 random chars) and `"timestamp"` (unix millis)
3. Encrypt with AES/CBC/ZeroBytePadding using session key/IV
4. Base64 encode
5. Wrap: `{"data": "<base64_ciphertext>"}`

**Response decryption:**
1. Try JSON parse — if valid, response is unencrypted (pass through)
2. Otherwise: Base64 decode -> AES/CBC/ZeroBytePadding decrypt -> parse as JSON

**Bypassed for:** GET requests, PUT requests, multipart uploads

### 3.3 Standard Response Envelope

All responses use `BaseResp<T>`:

```json
{
  "code": 200,
  "successful": true,
  "message": "success",
  "data": { ... }
}
```

| Code | Meaning |
|------|---------|
| 200 | Success |
| 401 | Token expired / unauthorized -> forces logout |
| 402 | Account cancelled -> forces logout |
| 5000 | General server error |
| 5002 | Validation error |
| 5003 | Business logic error |
| 5004 | Not found |
| 5006 | Silent error (no toast shown) |
| 5029 | Device unbound (triggers local unbind event) |
| 5050 | Rate limited |
| 5051 | Account cancelled |
| 5055 | Feature unavailable |
| 10004 | Custom error |

For paginated responses, `ListResp<T>` adds:
```json
{
  "code": 200,
  "data": {
    "records": [ ... ],
    "total": 100,
    "current": 1,
    "size": 20
  }
}
```

---

## 4. Authentication Flow

### 4.1 Login

```
POST /login
Header: Device-Id: <android_device_id>
Body: { "email": "user@example.com", "password": "<password>" }
Response: BaseResp<TokenIdInfo>
```

**TokenIdInfo:**
```json
{
  "token": "<jwt_like_auth_token>",
  "serialNumber": "<user_serial>",
  "tokenExpires": 86400,
  "domain": ["https://apiamerica.aiper.com/"],
  "countryId": 166,
  "abnormalDeviceLogin": false,
  "abnormalLocationLogin": false
}
```

The `token` is used in the `token` HTTP header for all subsequent requests. The `domain` list sets the user's API base URL.

**Token validity:** Checked as `currentTime <= tokenTimestamp + (tokenExpires * 0.8)`. At 80% of expiry, the app proactively refreshes.

### 4.2 Token Refresh

```
POST users/token/refresh
Header: token: <current_token>
Response: BaseResp<TokenIdInfo>
```

### 4.3 Registration

```
POST /sendEmail         -> sends verification code, returns expiry timestamp
POST /sendEmailExpire   -> sends verification code with longer expiry
POST /checkEmailVerificationCode -> verifies the code
POST /registerByCode    -> creates account with verified code
```

### 4.4 Password Reset

```
POST /forgetPwd
Body: { "email": "...", "code": "...", "password": "..." }
```

### 4.5 Logout

```
POST /users/loginOut
```

### 4.6 Token Expiry Handling

The `TokenExpiredInterceptor` monitors all HTTP responses. On codes 401, 402, or 5051, it forces a logout: clears credentials, navigates to login screen.

---

## 5. REST API Endpoints

### 5.1 Device Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/equipment/getEquipment` | List all user's devices |
| POST | `/equipment/getEquipmentInfo` | Get device info by SN |
| POST | `/equipment/existEquipment` | Check if user has any devices |
| POST | `/equipment/insertEquipment` | Register/bind a new device |
| POST | `/equipment/unbundle` | Unbind a device |
| POST | `/equipment/setName` | Rename a device |
| POST | `/equipment/checkEquipmentExist` | Check if SN exists in system |
| POST | `/equipment/checkEquipmentBindingStatus` | Check if device is bound |
| POST | `/equipment/checkEquipmentOnlineStatus` | Check cloud online status |
| POST | `/equipment/setEquipmentAutoUpgrade` | Toggle auto-OTA |
| POST | `/equipment/registerEquipmentToAWS` | Register device with AWS IoT |
| POST | `/equipment/configResultSubmit` | Submit WiFi config result |
| POST | `/equipment/locks/info/lock` | Get device lock info |
| POST | `/equipment/locks/content/v2` | Get lock content |
| POST | `/users/verificationToken` | Verify auth token validity |
| POST | `/users/getOpenIdToken` | **Get AWS IoT credentials** (critical for MQTT) |

### 5.2 Equipment Places (Locations/Rooms)

| Method | Path | Description |
|--------|------|-------------|
| POST | `equipment/getEquipmentPlaceList` | List all places |
| POST | `equipment/insertEquipmentPlace` | Create a place |
| POST | `equipment/updateEquipmentPlace` | Update a place |
| POST | `equipment/deleteEquipmentPlace` | Delete a place |
| POST | `equipment/getEquipmentByPlaceId` | Get devices in a place |
| POST | `equipment/moveEquipmentPlace` | Move device to a place |
| POST | `equipment/getEquipmentPlaceNum` | Get device count in place |
| POST | `equipment/getOneEquipmentPlace` | Get single place details |

### 5.3 Family Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/family/v1/getFamilyAllInfo` | Get all family/home info |
| POST | `/family/v1/addEquipmentToDefaultPlaceByFamilyId` | Add device to family |
| POST | `/family/v1/bluetoothAddEquipmentToDefaultPlaceByFamilyId` | Add device via BLE |

### 5.4 Clean Records & Statistics

| Method | Path | Description |
|--------|------|-------------|
| POST | `/swimming/v2/getCleanTimeBySn` | Get paginated clean records |
| POST | `/swimming/v2/statisticsCleanTimeBySn` | Get clean statistics |
| POST | `/swimming/getAllCleanRecordId` | Get all record IDs |
| POST | `/x9/clean/page/list` | X9 series clean records (paginated) |
| POST | `/x9/clean/detail` | X9 clean record detail |
| POST | `/x9/clean/statistics` | X9 clean statistics |
| POST | `/equipmentCleanRecord/gen4/n30n31t30/page` | Gen4 clean records |
| POST | `/equipmentCleanRecord/gen4/n30n31t30/detail` | Gen4 record detail |
| POST | `/equipmentCleanRecord/gen4/n30n31t30/statistic` | Gen4 statistics |
| POST | `/X30/clean/page/list` | X30 clean records |
| POST | `/X30/clean/detail` | X30 record detail |
| POST | `/X30/clean/statistics` | X30 statistics |
| POST | `/device/battery/infos/calendar/list` | Battery history calendar |
| POST | `/device/battery/infos/battery/statistics` | Battery stats |

### 5.5 Scheduling & Clean Plans

| Method | Path | Description |
|--------|------|-------------|
| POST | `/poolRobot/getTimedTask` | Get scheduled cleaning tasks |
| POST | `/deviceCleanPlan/getCleanPlanByDeviceSn` | Get device clean plan |
| POST | `/deviceCleanPlan/n30/insertDeviceCleanPlan` | Create clean plan |
| POST | `/deviceCleanPlan/disableDeviceCleanPlan` | Disable clean plan |

### 5.6 AI Navium Plans (AI-assisted cleaning)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/aiNavium/getAiNaviumPlan` | Get AI cleaning plan |
| POST | `/aiNavium/computeAiNaviumPlan` | Compute new AI plan |
| POST | `/aiNavium/deleteAiNaviumPlan` | Delete AI plan |
| POST | `/aiNavium/enableAiNaviumPlan` | Enable AI plan |
| POST | `/aiNavium/updateAiNaviumPlan` | Update AI plan |
| POST | `/aiNavium/syncFailAiNaviumPlan` | Report sync failure |
| POST | `/aiNavium/checkCleanRecord` | Check cleaning record |

### 5.7 OTA / Firmware Updates

| Method | Path | Description |
|--------|------|-------------|
| POST | `/swimming/checkVersion` | Check firmware update (pool robots) |
| POST | `/x9/checkVersion` | Check firmware (X9 series) |
| POST | `/gateway/v1/checkVersion` | Check firmware (gateway) |
| POST | `/audio/checkVersion` | Check firmware (audio devices) |
| POST | `/swimming/otaHistory` | Report OTA start |
| POST | `/equipment/appTranspondServer` | Report OTA failure |
| POST | `/equipmentModel/checkNoSmartDeviceVersion` | Check non-smart device version |

### 5.8 Consumables / Maintenance

| Method | Path | Description |
|--------|------|-------------|
| POST | `/poolRobot/getConsumableList` | List consumable parts |
| POST | `/poolRobot/getComponentDetail` | Get component detail |
| POST | `/poolRobot/consumableUpdate` | Update consumable status |
| POST | `/poolRobot/maintainConsumableUpdate` | Update maintenance status |
| POST | `/poolRobot/getComponentExpireRemind` | Get expiry reminders |
| POST | `/poolRobot/getComponentGuideArticle` | Get maintenance guide |

### 5.9 Gateway Management (W2/HydroComm)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/gateway/v1/getGatewayBySubSn` | Get gateway for sub-device |
| POST | `/gateway/v1/getUnboundSubByGatewaySn` | List unbound sub-devices |
| POST | `/gateway/v1/getBoundSubByGatewaySn` | List bound sub-devices |
| POST | `/gateway/v1/addSub` | Bind sub-device to gateway |
| POST | `/gateway/v1/deleteSub` | Unbind sub-device |

### 5.10 User Account

| Method | Path | Description |
|--------|------|-------------|
| POST | `users/current` | Get current user info |
| POST | `users/updateNickname` | Update nickname |
| POST | `users/updateAvatar` | Update avatar URL |
| POST | `users/changePwd` | Change password |
| POST | `users/updateEmail` | Update email |
| POST | `/users/updateTempUnit` | Set temperature unit |
| POST | `/users/updateAreaUnit` | Set area unit |
| POST | `/users/updateLengthUnit` | Set length unit |
| POST | `/users/updateDepthUnit` | Set depth unit |
| POST | `/users/updateVolumeUnit` | Set volume unit |
| POST | `/users/updateWeightUnit` | Set weight unit |
| POST | `/users/updateHourFormat` | Set 12/24h format |
| POST | `/users/updateMeasurementSystem` | Set measurement system |
| POST | `/users/updateDeviceDisplayStyle` | Set device display style |
| POST | `/users/updateDeviceLogEnabled` | Toggle device logging |
| POST | `/users/unsubscribeAppV2` | Delete account |
| POST | `/users/getUserStatus` | Get user account status |
| POST | `/users/getMeasurementSystemList` | List measurement systems |
| POST | `/users/checkUserPwd` | Verify current password |
| POST | `/users/userChangeCountry` | Change user country |
| POST | `users/area/change` | Change user region |
| POST | `/checkAppVersion` | Check for app updates |

### 5.11 Messages & Notifications

| Method | Path | Description |
|--------|------|-------------|
| POST | `systemMessage/getSystemMessageList` | Get system messages |
| POST | `systemMessage/unreadSystem` | Get unread system messages |
| POST | `systemMessage/readAllSystemMessage` | Mark all as read |
| POST | `systemMessage/readSystemMessage` | Mark one as read |
| POST | `/systemMessage/unreadAll` | Check if any unread |
| POST | `equipmentMessage/getMessageEquipmentList` | Get device message list |
| POST | `equipmentMessage/getEquipmentMessagePage` | Get device messages (paginated) |
| POST | `equipmentMessage/readAllEquipmentMessageBySn` | Mark device messages read |
| POST | `equipmentMessage/readEquipmentMessage` | Mark one device message read |
| POST | `/aiperMessage/page` | Get Aiper robot messages |

### 5.12 Weather

| Method | Path | Description |
|--------|------|-------------|
| POST | `/weatherkit/getWeather` | Get weather for location |

### 5.13 Device Settings

| Method | Path | Description |
|--------|------|-------------|
| POST | `/device/settings/notice/setting/get` | Get notification settings |
| POST | `/device/settings/notice/setting/update` | Update notification settings |
| POST | `/device/settings/data/backup/get` | Get device data backup |
| POST | `/device/settings/data/backup/submit` | Submit device data backup |

---

## 6. AWS IoT MQTT Layer

### 6.1 Obtaining IoT Credentials

```
POST /users/getOpenIdToken
Response: BaseResp<OpenIdToken>
```

**OpenIdToken structure:**
```json
{
  "identityId": "us-east-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "iotEndpoint": "xxxxxxxxxxxxxx-ats.iot.us-east-1.amazonaws.com",
  "region": "us-east-1",
  "token": "<developer_authenticated_token>",
  "tokenDuration": 86400,
  "identityPoolId": "us-east-1:yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
}
```

### 6.2 MQTT Connection Setup

1. Create a `CognitoCachingCredentialsProvider` using the Developer Authenticated Identity flow:
   - Identity Pool ID from `OpenIdToken.identityPoolId`
   - Region from `OpenIdToken.region`
   - Custom developer provider with `identityId` and `token`
   - For China region: add logins map `{"cognito-identity.cn-north-1.amazonaws.com.cn": token}`

2. Create `AWSIotMqttManager`:
   - Client ID: `OpenIdToken.identityId`
   - Endpoint: `OpenIdToken.iotEndpoint`
   - Keep alive: 60 seconds
   - Reconnect retry limits: 5 min, 5 max
   - Max auto reconnect: unlimited (-1)

3. Also create `AWSIotDataClient` for HTTP-based shadow GET operations

4. Connection timeout: 3000ms

### 6.3 MQTT Topic Patterns

All topics use the device serial number (`sn`):

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `aiper/things/{sn}/upChan` | Device -> App | Command responses from device |
| `aiper/things/{sn}/downChan` | App -> Device | Commands sent to device |
| `$aws/things/{sn}/shadow/get` | App -> AWS | Request shadow state |
| `$aws/things/{sn}/shadow/get/accepted` | AWS -> App | Shadow state response |
| `$aws/things/{sn}/shadow/update` | App -> AWS | Update shadow desired state |
| `$aws/things/{sn}/shadow/update/accepted` | AWS -> App | Shadow update confirmed |
| `aiper/things/{sn}/shadow/report` | Device -> App | Shadow report (non-X9) |
| `aiper/things/{sn}/app/report` | Device -> App | Shadow report (X9 series) |
| `$aws/events/presence/disconnected/{identityId}` | AWS -> App | Device disconnect notification |
| `aiper/things/{sn}/cloudMessage/app/downChan` | Cloud -> App | Cloud push messages |
| `aiper/things/{sn}/cloud/app/downChan` | Cloud -> App | Cloud auth downstream |
| `aiper/things/{sn}/app/cloud/upChan` | App -> Cloud | Cloud auth upstream |

All subscriptions use **QoS 1**.

### 6.4 Reconnection Behavior

- On `ConnectionLost`: auto-reconnect if enabled and network available
- On `Reconnecting`: increment counter; every 5th attempt, refresh auth token via HTTP
- After 5+ failed attempts: force full reconnect cycle
- Credentials are refreshed via the `DeveloperProvider.refresh()` -> `update(identityId, token)` call

---

## 7. Device Shadow Model

The shadow follows the AWS IoT Shadow format:

```json
{
  "state": {
    "desired": { "<Shadow fields>" },
    "reported": { "<Shadow fields>" }
  },
  "metadata": { ... },
  "timestamp": 1716912345,
  "version": 42
}
```

### 7.1 Shadow Fields (43 sub-models, all nullable)

**Core State:**

| Field | Type | Description |
|-------|------|-------------|
| `Machine` | Object | Core device status |
| `NetStat` | Object | Network connectivity |
| `OpInfo` / `OpInfoReport` | Object | Operational info |
| `OtaStatus` / `OtaStatusReport` | Object | Firmware update status |
| `InwaterReport` | Object | Water detection |

**Machine sub-fields:**

| Field | Type | Description |
|-------|------|-------------|
| `cap` | Integer | Battery capacity percentage (0-100) |
| `mode` | Integer | Current cleaning mode code |
| `status` | Integer | Device operational status |
| `solar_status` | Integer | Solar charging status |
| `temp` | Integer | Temperature |
| `warn` | Integer | Warning flag (0 = no warning) |
| `warn_code` | Long | Specific warning/error code |
| `in_water` | Integer | Water detection (1 = in water) |
| `link` | Integer | Connection link type |
| `light` | Integer | Light on/off status |
| `visual` | Integer | Camera/visual status |

**NetStat sub-fields:**

| Field | Type | Description |
|-------|------|-------------|
| `ap` | Integer | AP mode active |
| `ble` | Integer | BLE connected |
| `cert` | Integer | AWS cert provisioned |
| `online` | Integer | Cloud connected (1 = online) |
| `bind` | Integer | Device bound to user |
| `sta` | Integer | WiFi station mode |

**OpInfo sub-fields:**

| Field | Type | Description |
|-------|------|-------------|
| `wifi_rssi` | Integer | WiFi signal strength |
| `bat` | Integer | Battery level |
| `status` | Integer | Operational status |
| `link` | Integer | Link indicator |
| `wifi_name` | String | Connected WiFi SSID |

**Report sub-models** (all appear as top-level Shadow fields):

| Field | Description |
|-------|-------------|
| `GetAlarmReport` | Active alarms/errors |
| `GetWorkModeReport` | Current work mode |
| `CycleWorkReport` | Scheduled cycle status |
| `GetRubbishBoxStatusReport` | Filter/dustbin status |
| `GatewayReport` | Gateway connection status |
| `AirBagStatusReport` | Air bag inflation |
| `SurfaceWaterReport` | Surface water conditions |
| `BottomRunModeReport` | Bottom cleaning mode |
| `SuperEcoReport` | Super eco mode status |
| `SpeedReport` | Motor speed |
| `AutomationTaskReport` | Automation task state |
| `AutomationTaskSettingReport` | Automation settings |
| `FinishTaskReport` | Task completion notification |
| `LifeTimeReport` | Component lifetime data |
| `VoiceBroadcastReport` | Voice announcement settings |
| `TaskEstimateReport` | Estimated task duration |

**Water Quality (W2/HydroComm gateway):**

| Field | Description |
|-------|-------------|
| `W2Info` | Water quality hub info |
| `W2WQS` / `WQSReport` / `WQS` | Water quality sensor readings |
| `W2WQSCalInfo` | Calibration info |
| `W2LifeTime` | Sensor lifetime |
| `W2AlarmMessage` | Water quality alarms |
| `W2SensorStatus` | Sensor status |
| `W2WakeupEnable` | Wake schedule |

### 7.2 Shadow Updates

Shadow updates use `copyNotNull()` merge semantics — only non-null fields in an incoming update overwrite the existing state. This means partial updates are the norm.

To read the current shadow:
1. Subscribe to `$aws/things/{sn}/shadow/get/accepted`
2. Publish empty message to `$aws/things/{sn}/shadow/get`
3. Parse the response as `ShadowResponse`

To update desired state:
1. Publish to `$aws/things/{sn}/shadow/update` with:
```json
{
  "state": {
    "desired": {
      "Machine": { "mode": 1 }
    }
  }
}
```

---

## 8. Command Protocol

### 8.1 Command Format

Commands sent via MQTT to `aiper/things/{sn}/downChan`:

**Standard format (most devices):**
```json
{
  "type": "<command_name>",
  "data": { ... },
  "chksum": 12345
}
```

**X9 format (X9, X1 Pro, WR, X30, X30SE, IrriSense SE):**
```json
{
  "<command_name>": { ... },
  "chksum": 12345
}
```

### 8.2 CRC16 Checksum

- Algorithm: CRC16 Modbus with lookup table
- Initial value: **39270** (0x9996)
- Computed over the JSON string *before* `chksum` is inserted

### 8.3 Command Encryption

Three encryption variants exist based on device generation:

**XOR encryption (legacy/default):**
- Key: `[0x12, 0x34, 0x56, 0x78]` (4-byte repeating XOR)
- Process: `base64encode(XOR(json_utf8, key)) + "\n"`
- Decryption: strip trailing `\n`, base64 decode, XOR with same key

**AES encryption (newer devices):**
- Key: `[0x02, 0x46, 0xB9, 0xC0, 0x0A, 0xF1, 0xEE, 0x10, 0xFA, 0x0C, 0xD0, 0x0D, 0x48, 0x00, 0xF5, 0x20]`
- Mode: AES/CBC/PKCS7Padding
- IV: random 16 bytes, prepended to ciphertext
- Wire format: `base64encode(iv_16_bytes || ciphertext)`

**ECDH encryption (newest devices):**
- Key exchange: ECDH with secp256r1 curve
- Shared secret from device public key + app private key
- Encryption: AES/CBC/PKCS7 with ECDH-derived key

### 8.4 Common Commands

Commands are defined in `CommonCmd.java`. Key commands for HA integration:

| Command Type | Data | Description |
|-------------|------|-------------|
| `Machine` | `{"mode": <int>}` | Set cleaning mode |
| `Machine` | `{"status": <int>}` | Start/stop/pause |
| `Machine` | `{"light": <int>}` | Toggle light |
| `OpInfo` | `{}` | Query operational info |
| `NetStat` | `{}` | Query network status |
| `OtaStatus` | `{}` | Query OTA status |
| `CycleWork` | `{...}` | Set cleaning schedule |
| `Machine` | `{"cmd": "AT+<name>=<args>", "sn": "<sn>"}` | AT command (gateway) |

### 8.5 Cleaning Modes

**Gen2 devices (Surfers, older Scubas):**

| Mode Code | Name |
|-----------|------|
| 1 | Auto (FloorWall) |
| 2 | Floor |
| 3 | Wall |
| 4 | Waterline |
| 5 | Eco |

**Gen4 devices (newer Scubas, X30, etc.):**

| Mode | Description |
|------|-------------|
| Auto | Automatic cleaning |
| Floor | Floor only |
| Wall | Wall only |
| Waterline | Waterline cleaning |
| Skimming | Surface skimming |
| Random | Random path |
| MultiZone | Multi-zone cleaning |
| AINavium | AI-assisted navigation |
| Cycle | Scheduled cycle |
| Eco | Eco mode |
| Underwater | Underwater cleaning |
| Visual | Vision-guided |
| Copilot | Co-pilot mode |
| Customize | Custom mode group |
| VisionPath | Vision path group |

**Clean Power levels:**

| Code | Name | Intensity |
|------|------|-----------|
| 1 | Smart | Standard (2) |
| 2 | Max | Max (3) |
| 3 | Eco | Eco (1) |
| 4 | SuperEco | Lowest |

---

## 9. Device Types & Serial Number Prefixes

The first 2 characters of the serial number identify the device type:

| SN Prefix | Device Type | Product Names |
|-----------|-------------|---------------|
| S1, M1, 1S, 1M | S1 (Surfer) | Surfer S1, Surfer M1, EcoSurfer S1/M1 |
| S2, M2, 2S, SM, SW, SP | S2 (Surfer) | Surfer S2, Surfer M2, EcoSurfer S2/M2/W2/P1 |
| B3 | SurferB30 | Surfer B30, EcoSurfer Senti |
| NL, N0, N6 | ScubaN30 | Scuba S3 |
| N1, N2, N3 | ScubaN31 | Scuba V3, Scuba N31, Scuba N3 |
| T3 | ScubaT30 | Scuba T30 |
| 51, 53, 52, X5, XS | X5ProMax | Scuba N1 2025, N1 Plus, S1 2025, N1, S1 |
| X6, XN, XU, 6P, 7P | X6 | Scuba S1 Pro, N1 Pro, N1 Ultra, P1 Pro, P1 Ultra |
| T1, TM | ScubaX1 | Scuba X1, Scuba N1 Max |
| TX | ScubaX1Pro | Scuba X1 Pro |
| X9 | X9 | Scuba X1 Pro Max |
| X0 | X30 | Scuba V3 Ultra |
| XE | X30SE | Scuba V3 Pro |
| W2, WP, WE | W2 | HydroComm, HydroComm Pro/Pure, HydroHub, HydroHub Pro |
| WR, WG, WC | WR | IrriSense, Irrigo, IrriSense 2/N2/II/Chromatic |
| WL | IrriSenseSE | IrriSense 2 SE |
| AA | Pooljoy | BS270 |

**Series groupings:**
- **X9 Series** (uses X9 command format): X9, ScubaX1Pro, WR, X30, X30SE, IrriSenseSE
- **ScubaN30 Series**: ScubaN30, ScubaN31
- **Surfers**: S1, S2, SurferB30

---

## 10. Local Device API

When a device is in AP mode (during WiFi setup), it exposes a local HTTP server:

```
GET http://192.168.4.1:8001/GetCleanRecord
Response: CleanMapRecords (JSON)
```

This is used to retrieve cleaning map records directly from the device without cloud connectivity.

---

## 11. Home Assistant Integration Notes

### 11.1 Recommended Architecture

```
HA Integration
  |
  +-- AiperCloudClient (REST API)
  |     - Login / token management
  |     - Device listing
  |     - Clean records / statistics
  |     - Schedule management
  |
  +-- AiperMqttClient (AWS IoT)
        - Real-time state updates (shadow)
        - Device control (start/stop/mode)
        - Online/offline detection
```

### 11.2 Minimum Viable Integration

For a basic HA integration, you need:

1. **Login** -> `POST /login` with email/password
2. **List devices** -> `POST /equipment/getEquipment`
3. **Get IoT credentials** -> `POST /users/getOpenIdToken`
4. **Connect MQTT** -> AWS IoT with Cognito Developer Auth
5. **Subscribe to shadows** -> `$aws/things/{sn}/shadow/get/accepted` and `aiper/things/{sn}/shadow/report`
6. **Get initial state** -> Publish to `$aws/things/{sn}/shadow/get`
7. **Control device** -> Publish commands to `aiper/things/{sn}/downChan`

### 11.3 Entities to Expose

| Entity Type | Source | Fields |
|-------------|--------|--------|
| `vacuum` | Shadow.Machine | status, mode, battery (cap) |
| `sensor` (battery) | Shadow.Machine.cap | Battery percentage |
| `sensor` (wifi_signal) | Shadow.OpInfo.wifi_rssi | WiFi RSSI |
| `binary_sensor` (online) | Shadow.NetStat.online | Cloud connectivity |
| `binary_sensor` (in_water) | Shadow.Machine.in_water | Water detection |
| `sensor` (temperature) | Shadow.Machine.temp | Device temperature |
| `switch` (light) | Shadow.Machine.light | Device light |
| `sensor` (warn_code) | Shadow.Machine.warn_code | Error/warning code |
| `select` (clean_mode) | Shadow.Machine.mode | Cleaning mode selection |
| `sensor` (water_quality) | Shadow.W2WQS | Water quality (W2 gateway) |

### 11.4 Key Challenges

1. **HTTP Encryption**: Every REST request must be AES-encrypted with RSA key exchange. This is the biggest implementation hurdle — you must replicate the `EncryptInterceptor` logic.

2. **AWS IoT Authentication**: Uses Developer Authenticated Identities, not standard Cognito. You need the `boto3` or `awsiotsdk` Python library with custom auth.

3. **MQTT Command Encryption**: Commands need XOR, AES, or ECDH encryption depending on device generation. Start with XOR (simplest, covers older devices).

4. **CRC16 Checksum**: Must implement the Modbus CRC16 with initial value 39270.

5. **Token Refresh**: The auth token expires. Implement proactive refresh at 80% of `tokenExpires`.

6. **Regional Servers**: Must handle the correct regional API server based on user's country.

### 11.5 Python Pseudocode: Login + Get Devices

```python
import requests
import json
import base64
import os
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

RSA_PUBLIC_KEY = "MIGfMA0GCSqGSIb3DQEBA..."  # international key

class AiperClient:
    def __init__(self, base_url="https://apiamerica.aiper.com/"):
        self.base_url = base_url
        self.token = ""
        self.aes_key = os.urandom(16)
        self.aes_iv = os.urandom(16)
        self.encrypt_key = self._rsa_encrypt_session_key()

    def _rsa_encrypt_session_key(self):
        key_data = json.dumps({"key": self.aes_key.hex(), "iv": self.aes_iv.hex()})
        rsa_key = RSA.import_key(base64.b64decode(RSA_PUBLIC_KEY))
        cipher = PKCS1_v1_5.new(rsa_key)
        return base64.b64encode(cipher.encrypt(key_data.encode())).decode()

    def _encrypt_body(self, body: dict) -> dict:
        body["nonce"] = os.urandom(4).hex()[:4]
        body["timestamp"] = int(time.time() * 1000)
        plaintext = json.dumps(body).encode()
        # pad to AES block size with zeros
        padded = plaintext + b'\x00' * (16 - len(plaintext) % 16)
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_iv)
        ct = cipher.encrypt(padded)
        return {"data": base64.b64encode(ct).decode()}

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "version": "3.3.2",
            "os": "android",
            "charset": "UTF-8",
            "Accept-Language": "en",
            "zoneId": "America/New_York",
            "token": self.token,
            "encryptKey": self.encrypt_key,
        }

    def login(self, email, password):
        body = {"email": email, "password": password}
        resp = requests.post(
            self.base_url + "login",
            json=self._encrypt_body(body),
            headers=self._headers()
        )
        data = self._decrypt_response(resp)
        self.token = data["data"]["token"]
        return data

    def get_devices(self):
        resp = requests.post(
            self.base_url + "equipment/getEquipment",
            json=self._encrypt_body({}),
            headers=self._headers()
        )
        return self._decrypt_response(resp)

    def get_iot_credentials(self):
        resp = requests.post(
            self.base_url + "users/getOpenIdToken",
            json=self._encrypt_body({}),
            headers=self._headers()
        )
        return self._decrypt_response(resp)
```

### 11.6 MQTT Command Example (XOR Encryption)

```python
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

def encrypt_command(cmd_type: str, data: dict = None) -> bytes:
    msg = {"type": cmd_type}
    if data:
        msg["data"] = data
    json_str = json.dumps(msg)
    checksum = crc16_modbus(json_str.encode())
    msg["chksum"] = checksum
    json_bytes = json.dumps(msg).encode()
    # XOR encrypt
    encrypted = bytes(b ^ XOR_KEY[i % 4] for i, b in enumerate(json_bytes))
    return base64.b64encode(encrypted) + b"\n"

# Example: Start auto cleaning
payload = encrypt_command("Machine", {"mode": 1, "status": 1})
# Publish to: aiper/things/{sn}/downChan
```

---

## Appendix A: Response Code Reference

| Code | Constant | Meaning |
|------|----------|---------|
| 200 | code_200 | Success |
| 401 | code_401 | Unauthorized (forces logout) |
| 5000 | code_5000 | Server error |
| 5002 | code_5002 | Validation error |
| 5003 | code_5003 | Business error |
| 5004 | code_5004 | Not found |
| 5006 | code_5006 | Silent error |
| 5029 | code_5029 | Device unbound |
| 5050 | code_5050 | Rate limited |
| 5055 | code_5055 | Feature unavailable |
| 10004 | code_10004 | Custom error |

## Appendix B: BLE UUIDs

Each device type defines BLE service/characteristic UUIDs for direct Bluetooth control. These are defined in `DeviceType.java` but are out of scope for a cloud-based HA integration. They would be relevant for a Bluetooth proxy integration.

## Appendix C: Disclaimer

This specification was reverse-engineered from the Aiper Android app v3.3.2 for personal/educational use and potential Home Assistant integration development. API endpoints, encryption schemes, and protocols may change in future app versions. Use at your own risk. This document is not affiliated with or endorsed by Aiper.
