from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_LOCAL_BIND_IP,
    DOMAIN,
    GATEWAY_COMMAND_PORT,
    GATEWAY_RESPONSE_PORT,
    SIGNAL_COVER_REGISTER,
    SIGNAL_COVER_STATE,
    SIGNAL_DEVICE_JOIN,
    SIGNAL_DEVICE_REPORT,
    SIGNAL_LIGHT_REGISTER,
    SIGNAL_LIGHT_STATE,
    SIGNAL_ZB_REPORT,
    SIGNAL_GATEWAY_ALIVE,
    SIGNAL_JOIN_WINDOW,
)

_LOGGER = logging.getLogger(__name__)


class UDPListener:
    """Listen for UDP messages from gateways and dispatch them."""

    def __init__(self, hass: HomeAssistant, bind_ip: str | None = None) -> None:
        self._hass = hass
        self._bind_ip = bind_ip or ""
        self._transport: asyncio.DatagramTransport | None = None

    async def async_start(self) -> None:
        if self._transport is not None:
            return

        loop = asyncio.get_running_loop()
        def _bind_socket() -> socket.socket:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            bind_host = self._bind_ip or "0.0.0.0"
            sock.bind((bind_host, GATEWAY_RESPONSE_PORT))
            return sock

        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._hass),
            sock=_bind_socket(),
        )
        _LOGGER.debug(
            "UDP listener started on %s:%s",
            self._bind_ip or "0.0.0.0",
            GATEWAY_RESPONSE_PORT,
        )

    async def async_stop(self) -> None:
        if self._transport is None:
            return

        self._transport.close()
        self._transport = None
        _LOGGER.debug("UDP listener stopped")


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def datagram_received(self, data: bytes, addr) -> None:
        raw_preview = data.decode(errors="replace")
        _LOGGER.debug("UDP datagram from %s len=%d raw=%r", addr, len(data), raw_preview)
        try:
            payload = json.loads(data.decode())
        except json.JSONDecodeError:
            _LOGGER.debug("Discarding non-JSON UDP payload from %s", addr)
            return
        _LOGGER.debug("UDP JSON payload from %s: %s", addr, payload)

        msg_type = str(payload.get("type", "")).lower()
        if msg_type == "light_register":
            async_dispatcher_send(self._hass, SIGNAL_LIGHT_REGISTER, payload)
        elif msg_type == "light_state":
            async_dispatcher_send(self._hass, SIGNAL_LIGHT_STATE, payload)
        elif msg_type == "cover_register":
            async_dispatcher_send(self._hass, SIGNAL_COVER_REGISTER, payload)
        elif msg_type == "cover_state":
            async_dispatcher_send(self._hass, SIGNAL_COVER_STATE, payload)
        elif msg_type == "device_join":
            async_dispatcher_send(self._hass, SIGNAL_DEVICE_JOIN, payload)
        elif msg_type == "device_report":
            async_dispatcher_send(self._hass, SIGNAL_DEVICE_REPORT, payload)
        elif msg_type == "zigbee_report":
            async_dispatcher_send(self._hass, SIGNAL_ZB_REPORT, payload)
        elif msg_type == "gateway_alive":
            async_dispatcher_send(self._hass, SIGNAL_GATEWAY_ALIVE, payload)
        elif msg_type == "join_window":
            async_dispatcher_send(self._hass, SIGNAL_JOIN_WINDOW, payload)
        else:
            _LOGGER.debug("Ignoring unsupported UDP message type '%s'", msg_type)


async def async_send_udp_command(
    hass: HomeAssistant, host: str, payload: dict[str, Any], port: int | None = None
) -> None:
    """Send a JSON payload to the given host via UDP."""

    target_port = port or GATEWAY_COMMAND_PORT
    data = json.dumps(payload).encode()
    _LOGGER.debug("UDP send to %s:%s payload=%s", host, target_port, payload)

    bind_ip = ""
    if DOMAIN in hass.data:
        bind_ip = hass.data[DOMAIN].get(CONF_LOCAL_BIND_IP, "")

    def _send() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if bind_ip:
                sock.bind((bind_ip, 0))
            sock.sendto(data, (host, target_port))

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send)
