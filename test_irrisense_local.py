#!/usr/bin/env python3
"""
IrriSense 2 BLE Test Script — Direct Local Bluetooth

Connects directly to an Aiper IrriSense 2 irrigation controller
using the local Bluetooth adapter via bleak.

Usage:
    python test_irrisense_local.py --scan-only
    python test_irrisense_local.py
    python test_irrisense_local.py --address CA:D8:96:77:D1:F4
"""

import argparse
import asyncio
import base64
import json

from bleak import BleakClient, BleakScanner

# ---------------------------------------------------------------------------
# Protocol layer (shared with ESPHome proxy version)
# ---------------------------------------------------------------------------

XOR_KEY = bytes([0x12, 0x34, 0x56, 0x78])

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

MAX_CHUNK = 152


def xor_crypt(data: bytes) -> bytes:
    return bytes([b ^ XOR_KEY[i % 4] for i, b in enumerate(data)])


def build_command(cmd_type: str, data: dict | None = None) -> bytes:
    cmd = {cmd_type: data or {}}
    json_bytes = json.dumps(cmd, separators=(",", ":")).encode("utf-8")
    encrypted = xor_crypt(json_bytes)
    encoded = base64.b64encode(encrypted).decode("ascii") + "\n"
    return encoded.encode("utf-8")


def parse_response(raw: bytes) -> dict:
    stripped = raw.rstrip(b"\n")
    padding = (4 - len(stripped) % 4) % 4
    decoded = base64.b64decode(stripped + b"=" * padding)
    decrypted = xor_crypt(decoded)
    data = json.loads(decrypted.decode("utf-8"))
    for key in data:
        if key not in ("chksum", "res"):
            return {"type": key, "data": data[key], "res": data.get("res")}
    return data


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

async def scan_for_aiper_devices(duration: float = 10.0, show_all: bool = False) -> list:
    label = "all BLE" if show_all else "Aiper"
    print(f"Scanning for {label} devices ({duration}s)...")

    devices = await BleakScanner.discover(timeout=duration, return_adv=True)

    results = []
    for device, adv_data in devices.values():
        name = device.name or adv_data.local_name or ""
        if show_all or name.lower().startswith("aiper"):
            results.append((device, name, adv_data.rssi))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


# ---------------------------------------------------------------------------
# GATT connection and command interface
# ---------------------------------------------------------------------------

class IrriSenseConnection:
    def __init__(self, client: BleakClient):
        self.client = client
        self._buffer = bytearray()
        self._response_event = asyncio.Event()
        self._last_response: dict | None = None

    async def connect(self):
        print(f"Connecting to {self.client.address}...")
        await self.client.connect()

        if hasattr(self.client, '_acquire_mtu'):
            try:
                await self.client._acquire_mtu()
            except Exception:
                pass
        print(f"  Connected (MTU={self.client.mtu_size})")

        await self._subscribe_notifications()
        print("  Ready")

    async def _subscribe_notifications(self):
        print("  Subscribing to NUS TX notifications...")
        await self.client.start_notify(NUS_TX_UUID, self._on_notify)

    UNSOLICITED_TYPES = {"realTimeProgress", "AbnormalReminder", "Alarm"}

    def _on_notify(self, sender, data: bytearray):
        self._buffer.extend(data)
        if self._buffer.endswith(b"\n"):
            try:
                response = parse_response(bytes(self._buffer))
                if response.get("type") in self.UNSOLICITED_TYPES:
                    print(f"\n  [unsolicited] {response.get('type')}: "
                          f"{json.dumps(response.get('data', {}), indent=2)}")
                else:
                    self._last_response = response
                    self._response_event.set()
            except Exception as e:
                print(f"\n  [notify] Failed to parse response: {e}")
                print(f"  [notify] Raw buffer ({len(self._buffer)} bytes): {self._buffer!r}")
            self._buffer.clear()

    async def send_command(self, cmd_type: str, data: dict | None = None, timeout: float = 10.0) -> dict | None:
        message = build_command(cmd_type, data)
        self._response_event.clear()
        self._last_response = None

        for i in range(0, len(message), MAX_CHUNK):
            chunk = message[i : i + MAX_CHUNK]
            await self.client.write_gatt_char(NUS_RX_UUID, chunk, response=False)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return self._last_response
        except asyncio.TimeoutError:
            print(f"  No response within {timeout}s")
            return None

    async def disconnect(self):
        try:
            await self.client.stop_notify(NUS_TX_UUID)
        except Exception:
            pass
        await self.client.disconnect()
        print("Disconnected")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------

SAFE_COMMANDS = [
    ("DevInfo", None, "Device info (firmware, model, serial)"),
    ("OpInfo", None, "Operational status"),
    ("workInfo", None, "Current work status / progress"),
    ("_dump_maps", None, "Dump all map zones with points"),
    ("WrMapManageOverView", None, "List all maps (names, IDs, counts)"),
    ("getNozzle", None, "Get nozzle type setting"),
    ("GetSenseSwitch", None, "Get rain/weather sensor settings"),
    ("NetStat", None, "Network/connectivity status"),
    ("WrPlanOverview", None, "Get plan overview"),
    ("_dump_plans", None, "Dump all plan details"),
    ("locationGet", None, "Get device GPS location"),
    ("_location_vs_points", None, "Compare GPS location vs map point coords"),
    ("Alarm", None, "Get alarm status"),
    ("GetWrPesticides", None, "Get pesticide status"),
    ("WrRecordOverView", None, "Get irrigation record overview"),
    ("_query_point", None, "Query a single map point by id/type/index"),
    ("_dump_records", None, "Dump irrigation history records"),
]


async def dump_all_maps(conn: IrriSenseConnection):
    print("  Fetching map overview...")
    overview = await conn.send_command("WrMapManageOverView")
    if not overview or not overview.get("data"):
        print("  No map data available")
        return

    maps = overview["data"].get("map_list", [])
    print(f"  Found {len(maps)} map(s)\n")

    for m in maps:
        map_id = m["id"]
        map_type = m["type"]
        total = m["point_total"]
        print(f"  === {m['name']} (id={map_id}, type={map_type}, {total} points) ===")

        points = []
        for i in range(total):
            resp = await conn.send_command("WrMapManageSingleInfo", {
                "id": map_id, "type": map_type, "point_index": i
            })
            if resp and resp.get("data"):
                pt = resp["data"].get("point_info", {})
                points.append(pt)
                print(f"    [{i:2d}] valve={pt.get('valve'):5d}  rotate={pt.get('rotate'):5d}"
                      f"  x={pt.get('x'):6d}  y={pt.get('y'):6d}"
                      f"  waterpress={pt.get('waterpress', 0):.1f}")
            else:
                print(f"    [{i:2d}] (no response)")
        print()


WEEKDAYS = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


async def dump_all_plans(conn: IrriSenseConnection):
    print("  Fetching plan overview...")
    overview = await conn.send_command("WrPlanOverview")
    if not overview or not overview.get("data"):
        print("  No plan data available")
        return

    used = overview["data"].get("used_ids", [])
    if not used:
        print("  No plans configured")
        return

    print(f"  Found {len(used)} plan(s)\n")
    for plan_id in used:
        resp = await conn.send_command("WrPlanDetail", {"plan_id": plan_id})
        if resp and resp.get("data"):
            d = resp["data"]
            mi = d.get("map_info", {})
            wc = d.get("work_ctrl", {})
            tc = d.get("time_ctrl", {})
            days = ", ".join(WEEKDAYS.get(i, f"?{i}") for i in tc.get("weekdays", []))
            repeat = "weekly" if tc.get("repeat_type") == 1 else f"repeat={tc.get('repeat_type')}"
            enabled = "ON" if d.get("enabled") else "OFF"
            print(f"  Plan {plan_id}: {mi.get('name', '?')} [{enabled}]")
            print(f"    Schedule: {days} at {tc.get('start_time', '?')} ({repeat})")
            print(f"    Depth: {wc.get('depth', 0):.2f}  Point time: {wc.get('point_time', '?')} min")
            print(f"    Est. runtime: {d.get('estimated_time', '?')} min")
        else:
            print(f"  Plan {plan_id}: (no response)")
    print()


async def location_vs_points(conn: IrriSenseConnection):
    """Fetch device GPS and first point from each map to compare coordinate systems."""
    print("  Fetching device GPS location...")
    loc = await conn.send_command("locationGet")
    if loc and loc.get("data"):
        d = loc["data"]
        print(f"  Device GPS: lat={d.get('latitude')}, lon={d.get('longitude')}")
    else:
        print("  No GPS location available")

    print("\n  Fetching first point from each map...")
    overview = await conn.send_command("WrMapManageOverView")
    if not overview or not overview.get("data"):
        print("  No map data available")
        return

    maps = overview["data"].get("map_list", [])
    for m in maps:
        resp = await conn.send_command("WrMapManageSingleInfo", {
            "id": m["id"], "type": m["type"], "point_index": 0
        })
        if resp and resp.get("data"):
            pt = resp["data"].get("point_info", {})
            print(f"  {m['name']} point[0]: x={pt.get('x')}, y={pt.get('y')}, "
                  f"valve={pt.get('valve')}, rotate={pt.get('rotate')}")
        else:
            print(f"  {m['name']} point[0]: (no response)")
    print()


async def query_single_point(conn: IrriSenseConnection):
    """Interactively query a single map point."""
    overview = await conn.send_command("WrMapManageOverView")
    if not overview or not overview.get("data"):
        print("  No map data available")
        return

    maps = overview["data"].get("map_list", [])
    print("  Available maps:")
    for i, m in enumerate(maps, 1):
        print(f"    {i}. {m['name']} (id={m['id']}, type={m['type']}, "
              f"{m['point_total']} points)")

    map_choice = await asyncio.get_event_loop().run_in_executor(
        None, lambda: input("  Map number: "))
    idx = int(map_choice.strip()) - 1
    if not (0 <= idx < len(maps)):
        print("  Invalid selection")
        return
    m = maps[idx]

    pt_input = await asyncio.get_event_loop().run_in_executor(
        None, lambda: input(f"  Point index (0-{m['point_total']-1}): "))
    pt_idx = int(pt_input.strip())

    resp = await conn.send_command("WrMapManageSingleInfo", {
        "id": m["id"], "type": m["type"], "point_index": pt_idx
    })
    if resp and resp.get("data"):
        print(json.dumps(resp["data"], indent=2))
    else:
        print("  No response")
    print()


async def dump_records(conn: IrriSenseConnection):
    """Dump irrigation history records."""
    print("  Fetching record overview...")
    overview = await conn.send_command("WrRecordOverView")
    if not overview or not overview.get("data"):
        print("  No record data available")
        return

    data = overview["data"]
    print(json.dumps(data, indent=2))

    used_ids = data.get("used_ids", [])
    if not used_ids:
        print("  No records found")
        return

    print(f"\n  Found {len(used_ids)} record(s), fetching details...")
    for rec_id in used_ids:
        resp = await conn.send_command("WrRecordDetail", {"record_id": rec_id})
        if resp and resp.get("data"):
            print(f"\n  Record {rec_id}:")
            print(json.dumps(resp["data"], indent=2))
        else:
            print(f"\n  Record {rec_id}: (no response)")
    print()


def print_menu():
    print("Commands:")
    for i, (cmd, _, desc) in enumerate(SAFE_COMMANDS, 1):
        print(f"  {i:2d}. {cmd:25s} {desc}")
    print(f"  {len(SAFE_COMMANDS)+1:2d}. {'(raw command)':25s} Send a custom command")
    print(f"   h. {'help':25s} Show this menu")
    print(f"   q. {'quit':25s} Disconnect and exit")
    print()


async def interactive_loop(conn: IrriSenseConnection):
    print("\n--- IrriSense 2 Interactive Console ---")
    print_menu()

    while True:
        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, lambda: input(">> "))
        except (EOFError, KeyboardInterrupt):
            break

        choice = choice.strip()
        if not choice:
            continue
        if choice.lower() in ("q", "quit", "exit"):
            break
        if choice.lower() in ("h", "?", "help"):
            print_menu()
            continue

        cmd_type = None
        cmd_data = None

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(SAFE_COMMANDS):
                cmd_type, cmd_data, _ = SAFE_COMMANDS[idx - 1]
            elif idx == len(SAFE_COMMANDS) + 1:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("Command name: ")
                )
                raw = raw.strip()
                if not raw:
                    continue
                cmd_type = raw
                data_str = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("Data JSON (empty for none): ")
                )
                data_str = data_str.strip()
                if data_str:
                    try:
                        cmd_data = json.loads(data_str)
                    except json.JSONDecodeError as e:
                        print(f"  Invalid JSON: {e}")
                        continue
            else:
                print(f"  Invalid choice: {choice}")
                continue
        else:
            print(f"  Invalid choice: {choice}")
            continue

        if cmd_type == "_dump_maps":
            await dump_all_maps(conn)
            continue
        if cmd_type == "_dump_plans":
            await dump_all_plans(conn)
            continue
        if cmd_type == "_location_vs_points":
            await location_vs_points(conn)
            continue
        if cmd_type == "_query_point":
            await query_single_point(conn)
            continue
        if cmd_type == "_dump_records":
            await dump_records(conn)
            continue

        print(f"  Sending: {cmd_type} {json.dumps(cmd_data) if cmd_data else ''}")
        response = await conn.send_command(cmd_type, cmd_data)
        if response:
            print(f"  Response type: {response.get('type', '?')}")
            if response.get("res") is not None:
                print(f"  Result code: {response['res']}")
            data = response.get("data", {})
            if "available_ids" in data:
                data = {k: v for k, v in data.items() if k != "available_ids"}
            print(json.dumps(data, indent=2, ensure_ascii=False))
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="IrriSense 2 BLE test — direct local Bluetooth")
    parser.add_argument("--scan-only", action="store_true", help="Only scan for devices, don't connect")
    parser.add_argument("--address", default=None, help="BLE MAC address (skip scanning)")
    parser.add_argument("--scan-duration", type=float, default=10.0, help="Scan duration in seconds (default: 10)")
    parser.add_argument("--scan-all", action="store_true", help="Show all BLE devices, not just Aiper")
    parser.add_argument("--adapter", default=None, help="Bluetooth adapter (e.g., hci0, hci1)")
    args = parser.parse_args()

    if args.address:
        ble_address = args.address
    else:
        devices = await scan_for_aiper_devices(duration=args.scan_duration, show_all=args.scan_all)
        if not devices:
            print("No devices found.")
            return

        print(f"\nFound {len(devices)} device(s):")
        for i, (dev, name, rssi) in enumerate(devices, 1):
            print(f"  {i}. {name:30s} {dev.address}  RSSI={rssi}")

        if args.scan_only:
            return

        if len(devices) == 1:
            ble_address = devices[0][0].address
            print(f"\nAuto-selecting: {devices[0][1]}")
        else:
            choice = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("\nSelect device number: ")
            )
            idx = int(choice.strip()) - 1
            if not (0 <= idx < len(devices)):
                print("Invalid selection")
                return
            ble_address = devices[idx][0].address

    kwargs = {}
    if args.adapter:
        kwargs["adapter"] = args.adapter

    client = BleakClient(ble_address, **kwargs)
    conn = IrriSenseConnection(client)
    try:
        await conn.connect()

        print("\nSending DevInfo to verify connection...")
        response = await conn.send_command("DevInfo")
        if response:
            print(f"  Device responded: {response.get('type', '?')}")
            print(json.dumps(response.get("data", {}), indent=2, ensure_ascii=False))
        else:
            print("  No response to DevInfo — device may use a different protocol")

        await interactive_loop(conn)
    finally:
        await conn.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
