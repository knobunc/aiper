"""Tests for the Aiper IrriSense BLE protocol layer."""

import base64
import json

from custom_components.aiper.const import XOR_KEY
from custom_components.aiper.protocol import build_command, parse_response, xor_crypt


def test_xor_roundtrip():
    original = b"Hello, IrriSense!"
    assert xor_crypt(xor_crypt(original)) == original


def test_xor_empty():
    assert xor_crypt(b"") == b""


def test_xor_known_vector():
    data = bytes([0x00, 0x01, 0x02, 0x03])
    expected = bytes([d ^ XOR_KEY[i] for i, d in enumerate(data)])
    assert xor_crypt(data) == expected


def test_build_parse_roundtrip():
    result = parse_response(build_command("DevInfo", {"sn": "ABC123"}))
    assert result["type"] == "DevInfo"
    assert result["data"] == {"sn": "ABC123"}


def test_build_command_no_data():
    raw = build_command("workInfo")
    assert raw.endswith(b"\n")
    result = parse_response(raw)
    assert result["type"] == "workInfo"
    assert result["data"] == {}


def test_build_command_structure():
    raw = build_command("DevInfo", {"sn": "X"})
    decoded = base64.b64decode(raw.rstrip(b"\n"))
    decrypted = xor_crypt(decoded)
    payload = json.loads(decrypted)
    assert "DevInfo" in payload
    assert payload["DevInfo"]["sn"] == "X"


def test_parse_with_res():
    payload = {"DevInfo": {"sn": "123"}, "res": 0}
    json_bytes = json.dumps(payload, separators=(",", ":")).encode()
    encrypted = xor_crypt(json_bytes)
    raw = base64.b64encode(encrypted) + b"\n"
    result = parse_response(raw)
    assert result["type"] == "DevInfo"
    assert result["res"] == 0


def test_parse_with_chksum():
    payload = {"workInfo": {"status": 1}, "chksum": "abc", "res": 0}
    json_bytes = json.dumps(payload, separators=(",", ":")).encode()
    encrypted = xor_crypt(json_bytes)
    raw = base64.b64encode(encrypted) + b"\n"
    result = parse_response(raw)
    assert result["type"] == "workInfo"
    assert result["data"] == {"status": 1}
    assert result["res"] == 0
