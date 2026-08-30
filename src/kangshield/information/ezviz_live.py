"""In-memory EZVIZ live-endpoint provider with bounded refresh caching."""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from time import monotonic
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


API_BASE = "https://open.ys7.com"


def _post(path: str, fields: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(f"{API_BASE}{path}", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if str(payload.get("code")) != "200":
        raise RuntimeError(
            f"EZVIZ API {path} failed with code {payload.get('code')}: "
            f"{payload.get('msg')}"
        )
    return payload


def fetch_live_endpoint(
    device_serial: str,
    *,
    channel: int = 1,
    protocol: int = 4,
    quality: int = 1,
    support_h265: bool = True,
) -> str:
    """Fetch one expiring address without persisting credentials or the result."""

    app_key = os.environ.get("YS7_APP_KEY")
    app_secret = os.environ.get("YS7_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("set YS7_APP_KEY and YS7_APP_SECRET in the environment")
    if not device_serial.strip():
        raise RuntimeError("EZVIZ device serial is missing")
    token = _post(
        "/api/lapp/token/get", {"appKey": app_key, "appSecret": app_secret}
    )["data"]["accessToken"]
    address = _post(
        "/api/lapp/v2/live/address/get",
        {
            "accessToken": token,
            "deviceSerial": device_serial,
            "channelNo": str(channel),
            "protocol": str(protocol),
            "quality": str(quality),
            "supportH265": "1" if support_h265 else "0",
        },
    )["data"]["url"]
    if not address.startswith(("https://", "http://", "rtmp://")):
        raise RuntimeError(f"unexpected live address scheme for protocol={protocol}")
    return address


def fetch_playback_endpoint(
    device_serial: str,
    *,
    started_at: datetime,
    ended_at: datetime,
    channel: int = 1,
    protocol: int = 3,
    quality: int = 2,
    timezone_name: str = "Asia/Shanghai",
) -> str:
    """Fetch one short-lived cloud-recording URL without persisting credentials."""

    app_key = os.environ.get("YS7_APP_KEY")
    app_secret = os.environ.get("YS7_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("set YS7_APP_KEY and YS7_APP_SECRET in the environment")
    if not device_serial.strip():
        raise RuntimeError("EZVIZ device serial is missing")
    if started_at.tzinfo is None or ended_at.tzinfo is None:
        raise ValueError("playback times must be timezone-aware")
    if ended_at <= started_at:
        raise ValueError("playback end must be after start")
    local_zone = ZoneInfo(timezone_name)
    token = _post(
        "/api/lapp/token/get", {"appKey": app_key, "appSecret": app_secret}
    )["data"]["accessToken"]
    address = _post(
        "/api/lapp/v2/live/address/get",
        {
            "accessToken": token,
            "deviceSerial": device_serial.strip(),
            "channelNo": str(channel),
            "protocol": str(protocol),
            "quality": str(quality),
            "type": "3",
            "startTime": started_at.astimezone(local_zone).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "stopTime": ended_at.astimezone(local_zone).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "supportH265": "0",
        },
    )["data"]["url"]
    parsed = urlsplit(address)
    allowed_hosts = ("ys7.com", "ezvizlife.com", "ezviz.com", "eziot.com")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not any(
            parsed.hostname == suffix or parsed.hostname.endswith(f".{suffix}")
            for suffix in allowed_hosts
        )
    ):
        raise RuntimeError("unexpected EZVIZ playback address")
    return address


class EzvizEndpointProvider:
    """Keep an endpoint only in memory and refresh it after TTL or stream failure."""

    def __init__(self, device_serial: str, *, refresh_seconds: float = 1800) -> None:
        if refresh_seconds <= 0:
            raise ValueError("EZVIZ endpoint refresh_seconds must be positive")
        if not device_serial.strip():
            raise ValueError("EZVIZ device serial must not be empty")
        self._device_serial = device_serial.strip()
        self.refresh_seconds = float(refresh_seconds)
        self._endpoint: str | None = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            now = monotonic()
            if (
                self._endpoint is None
                or now - self._fetched_at >= self.refresh_seconds
            ):
                self._endpoint = fetch_live_endpoint(self._device_serial)
                self._fetched_at = now
            return self._endpoint

    def invalidate(self) -> None:
        with self._lock:
            self._endpoint = None
            self._fetched_at = 0.0


class EzvizPlaybackProvider:
    """Resolve an event window to a transient cloud URL only when the owner asks."""

    def __init__(
        self,
        device_serial: str,
        *,
        channel: int = 1,
        timezone_name: str = "Asia/Shanghai",
    ) -> None:
        if not device_serial.strip():
            raise ValueError("EZVIZ device serial must not be empty")
        if channel <= 0:
            raise ValueError("EZVIZ channel must be positive")
        ZoneInfo(timezone_name)
        self._device_serial = device_serial.strip()
        self.channel = channel
        self.timezone_name = timezone_name

    def __call__(self, started_at: datetime, ended_at: datetime) -> str:
        return fetch_playback_endpoint(
            self._device_serial,
            started_at=started_at,
            ended_at=ended_at,
            channel=self.channel,
            timezone_name=self.timezone_name,
        )


def provider_from_environment(
    variable_name: str = "KANG_DEVICE_SERIAL", *, refresh_seconds: float = 1800
) -> EzvizEndpointProvider:
    if not variable_name or any(character.isspace() for character in variable_name):
        raise ValueError("device serial environment variable name is invalid")
    serial = os.environ.get(variable_name)
    if serial is None or not serial.strip():
        raise RuntimeError(f"set {variable_name} in the private environment")
    return EzvizEndpointProvider(serial, refresh_seconds=refresh_seconds)


def playback_provider_from_environment(
    variable_name: str = "KANG_DEVICE_SERIAL",
    *,
    timezone_variable_name: str = "KANG_DEVICE_TIMEZONE",
) -> EzvizPlaybackProvider:
    if not variable_name or any(character.isspace() for character in variable_name):
        raise ValueError("device serial environment variable name is invalid")
    serial = os.environ.get(variable_name)
    if serial is None or not serial.strip():
        raise RuntimeError(f"set {variable_name} in the private environment")
    timezone_name = os.environ.get(timezone_variable_name, "Asia/Shanghai").strip()
    return EzvizPlaybackProvider(serial, timezone_name=timezone_name)
