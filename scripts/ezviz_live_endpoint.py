#!/usr/bin/env python3
"""Fetch a fresh EZVIZ FLV live endpoint for one device.

Security rules (docs/device-data/streaming-and-media.md):
- appKey/appSecret arrive only via YS7_APP_KEY / YS7_APP_SECRET env vars;
- the resulting live address is printed to stdout exactly once so the caller
  can capture it into KANG_STREAM_ENDPOINT; nothing is persisted, logged or
  written to any file;
- live addresses expire, so this helper is run once per capture session.

Usage:
    export YS7_APP_KEY=... YS7_APP_SECRET=...
    export KANG_STREAM_ENDPOINT="$(
        .venv/bin/python scripts/ezviz_live_endpoint.py <device-serial>
    )"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

API_BASE = "https://open.ys7.com"


def _post(path: str, fields: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(f"{API_BASE}{path}", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())
    if str(payload.get("code")) != "200":
        # Error codes/messages only; never echo request material.
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
    app_key = os.environ.get("YS7_APP_KEY")
    app_secret = os.environ.get("YS7_APP_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("set YS7_APP_KEY and YS7_APP_SECRET in the environment")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device_serial")
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument(
        "--protocol",
        type=int,
        default=4,
        help="4 = FLV over HTTP(S) (validated route); 3 = HLS",
    )
    parser.add_argument("--quality", type=int, default=1)
    args = parser.parse_args()
    endpoint = fetch_live_endpoint(
        args.device_serial,
        channel=args.channel,
        protocol=args.protocol,
        quality=args.quality,
    )
    print(endpoint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
