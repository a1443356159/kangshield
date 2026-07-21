from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


SENSITIVE_FRAGMENTS = (
    "accesstoken",
    "access_token",
    "appkey",
    "app_key",
    "secret",
    "password",
    "verifycode",
    "verificationcode",
    "deviceserial",
    "device_serial",
    "serialnumber",
    "devicename",
    "device_name",
    "phone",
    "mobile",
    "username",
    "eldername",
    "姓名",
    "电话",
    "手机号",
    "序列号",
    "验证码",
    "密钥",
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def safe_local_uri(path: Path, content_sha256: str | None = None) -> str:
    suffix = Path(path).suffix.lower()
    if content_sha256:
        opaque_name = f"asset_{content_sha256[:20]}{suffix}"
    else:
        digest = hashlib.sha256(Path(path).name.encode("utf-8")).hexdigest()
        opaque_name = f"path_{digest[:20]}{suffix}"
    return f"local-file://{quote(opaque_name)}"


def is_sensitive_key(key: str) -> bool:
    normalized = str(key).replace("-", "_").lower()
    return normalized in {"id", "name"} or any(
        fragment in normalized for fragment in SENSITIVE_FRAGMENTS
    )


def opaque_ref(namespace: str, value: str) -> tuple[str, bool]:
    salt = os.environ.get("KANGSHIELD_REF_SALT")
    if salt:
        digest = hmac.new(
            salt.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{namespace}_{digest[:16]}", True
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{namespace}_unsalted_{digest[:12]}", False


def redact_tree(value: Any) -> tuple[Any, int]:
    redacted_count = 0

    def visit(node: Any) -> Any:
        nonlocal redacted_count
        if isinstance(node, dict):
            result: dict[str, Any] = {}
            for key, item in node.items():
                if is_sensitive_key(str(key)):
                    result[str(key)] = "***REDACTED***"
                    redacted_count += 1
                else:
                    result[str(key)] = visit(item)
            return result
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    return visit(value), redacted_count
