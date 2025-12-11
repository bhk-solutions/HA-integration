from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from aiohttp import ClientError, ClientWebSocketResponse, WSMsgType
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

MessageCallback = Callable[[dict[str, Any]], None]
StatusCallback = Callable[[bool], None]


class GatewayClient:
    """Maintain a websocket connection to a BHK gateway."""

    def __init__(self, hass: HomeAssistant, mac: str, ip: str, port: int, path: str) -> None:
        self._hass = hass
        self._mac = mac
        self._ip = ip
        sanitized_path = path if path.startswith("/") else f"/{path}"
        self._url = f"ws://{ip}:{port}{sanitized_path}"
        self._session = async_get_clientsession(hass)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._socket: ClientWebSocketResponse | None = None
        self._connected = False
        self._message_listeners: list[MessageCallback] = []
        self._status_listeners: list[StatusCallback] = []

    @property
    def mac(self) -> str:
        return self._mac

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def async_start(self) -> None:
        """Start the background task that manages the websocket."""

        if self._task is None:
            self._stop_event.clear()
            self._task = self._hass.async_create_background_task(
                self._run(), f"{DOMAIN}-gateway-{self._mac}-ws"
            )

    async def async_stop(self) -> None:
        """Stop the websocket and background task."""

        self._stop_event.set()

        if self._socket is not None:
            await self._socket.close()
            self._socket = None

        if self._task:
            await self._task
            self._task = None

    async def async_send(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to the gateway."""

        if self._socket is None or not self._connected:
            raise ConnectionError("Gateway websocket is not connected")

        await self._socket.send_json(payload)

    def add_message_listener(self, callback: MessageCallback) -> CALLBACK_TYPE:
        self._message_listeners.append(callback)

        def _unsubscribe() -> None:
            if callback in self._message_listeners:
                self._message_listeners.remove(callback)

        return _unsubscribe

    def add_status_listener(self, callback: StatusCallback) -> CALLBACK_TYPE:
        self._status_listeners.append(callback)
        callback(self._connected)

        def _unsubscribe() -> None:
            if callback in self._status_listeners:
                self._status_listeners.remove(callback)

        return _unsubscribe

    async def _run(self) -> None:
        backoff = 1
        while not self._stop_event.is_set():
            try:
                _LOGGER.debug("Connecting to gateway %s at %s", self._mac, self._url)
                self._socket = await self._session.ws_connect(
                    self._url, heartbeat=30, timeout=10
                )
                self._set_connected(True)
                backoff = 1

                async for msg in self._socket:
                    if msg.type == WSMsgType.TEXT:
                        self._handle_message(msg.data)
                    elif msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.ERROR):
                        break
            except asyncio.CancelledError:
                break
            except (ClientError, asyncio.TimeoutError) as exc:
                _LOGGER.warning(
                    "Gateway %s websocket error: %s", self._mac, exc
                )
            finally:
                await self._close_socket()
                self._set_connected(False)

            if self._stop_event.is_set():
                break

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _close_socket(self) -> None:
        if self._socket is not None:
            try:
                await self._socket.close()
            except ClientError:
                pass
            self._socket = None

    def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.debug("Discarding non-JSON message from %s: %s", self._mac, raw)
            return

        for listener in list(self._message_listeners):
            listener(data)

    def _set_connected(self, connected: bool) -> None:
        if self._connected == connected:
            return

        self._connected = connected
        for listener in list(self._status_listeners):
            listener(connected)
