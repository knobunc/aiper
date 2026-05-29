"""BLE client for Aiper IrriSense — connect, send commands, receive responses."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import (
    COMMAND_TIMEOUT,
    MAX_CHUNK,
    NUS_RX_UUID,
    NUS_TX_UUID,
    UNSOLICITED_TYPES,
)
from .protocol import build_command, parse_response

_LOGGER = logging.getLogger(__name__)


class DeviceUnavailable(Exception):
    """Raised when the BLE device cannot be found."""


class IrriSenseClient:
    """BLE client for communicating with an IrriSense 2 device."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._hass = hass
        self._address = address
        self._client: BleakClient | None = None
        self._buffer = bytearray()
        self._response_event = asyncio.Event()
        self._last_response: dict[str, Any] | None = None
        self._unsolicited: list[dict[str, Any]] = []
        self._rssi: int | None = None

    @property
    def address(self) -> str:
        return self._address

    @property
    def rssi(self) -> int | None:
        return self._rssi

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Connect to the IrriSense device via BLE."""
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self._address.upper(), connectable=True
        )
        if ble_device is None:
            raise DeviceUnavailable(f"Device {self._address} not found")

        service_info = bluetooth.async_last_service_info(
            self._hass, self._address.upper(), connectable=True
        )
        if service_info:
            self._rssi = service_info.rssi

        self._client = await establish_connection(
            BleakClient, ble_device, self._address, max_attempts=3
        )

        self._buffer.clear()
        self._unsolicited.clear()
        await self._client.start_notify(NUS_TX_UUID, self._on_notify)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        """Handle incoming BLE notifications, buffering until newline."""
        self._buffer.extend(data)
        if not self._buffer.endswith(b"\n"):
            return
        try:
            response = parse_response(bytes(self._buffer))
            if response.get("type") in UNSOLICITED_TYPES:
                self._unsolicited.append(response)
                _LOGGER.debug(
                    "Unsolicited %s: %s",
                    response.get("type"),
                    response.get("data"),
                )
            else:
                self._last_response = response
                self._response_event.set()
        except Exception:
            _LOGGER.warning(
                "Failed to parse BLE response (%d bytes)",
                len(self._buffer),
                exc_info=True,
            )
        self._buffer.clear()

    async def send_command(
        self,
        cmd_type: str,
        data: dict[str, Any] | None = None,
        timeout: float = COMMAND_TIMEOUT,
    ) -> dict[str, Any] | None:
        """Send a command and wait for the response."""
        if not self._client or not self._client.is_connected:
            raise BleakError("Not connected")

        message = build_command(cmd_type, data)
        self._response_event.clear()
        self._last_response = None

        for i in range(0, len(message), MAX_CHUNK):
            chunk = message[i : i + MAX_CHUNK]
            await self._client.write_gatt_char(NUS_RX_UUID, chunk, response=False)

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            return self._last_response
        except TimeoutError:
            _LOGGER.debug("No response to %s within %ss", cmd_type, timeout)
            return None

    def drain_unsolicited(self) -> list[dict[str, Any]]:
        """Return and clear accumulated unsolicited notifications."""
        result = list(self._unsolicited)
        self._unsolicited.clear()
        return result

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.stop_notify(NUS_TX_UUID)
        except (BleakError, EOFError, TimeoutError):
            pass
        try:
            await self._client.disconnect()
        except (BleakError, EOFError, TimeoutError):
            pass
        self._client = None
