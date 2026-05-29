"""Aiper IrriSense BLE protocol: XOR encryption, command building, response parsing."""

from __future__ import annotations

import base64
import json
from typing import Any

from .const import XOR_KEY


def xor_crypt(data: bytes) -> bytes:
    """Symmetric XOR encryption/decryption with 4-byte key."""
    return bytes([b ^ XOR_KEY[i % 4] for i, b in enumerate(data)])


def build_command(cmd_type: str, data: dict[str, Any] | None = None) -> bytes:
    """Build an encrypted BLE command.

    Returns base64-encoded, XOR-encrypted JSON with newline terminator.
    """
    cmd = {cmd_type: data or {}}
    json_bytes = json.dumps(cmd, separators=(",", ":")).encode("utf-8")
    encrypted = xor_crypt(json_bytes)
    encoded = base64.b64encode(encrypted).decode("ascii") + "\n"
    return encoded.encode("utf-8")


def parse_response(raw: bytes) -> dict[str, Any]:
    """Parse a BLE response: base64 decode, XOR decrypt, JSON parse.

    Returns dict with keys: type, data, res.
    """
    stripped = raw.rstrip(b"\n")
    padding = (4 - len(stripped) % 4) % 4
    decoded = base64.b64decode(stripped + b"=" * padding)
    decrypted = xor_crypt(decoded)
    payload = json.loads(decrypted.decode("utf-8"))
    for key in payload:
        if key not in ("chksum", "res"):
            return {"type": key, "data": payload[key], "res": payload.get("res")}
    return dict(payload)
