from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    DeviceSummary,
    EvidenceLevel,
    EzvizSnapshotReport,
    Modality,
    PrivacyLevel,
    QualityIssue,
    Severity,
    SourceAsset,
    SourceType,
    ensure_source_evidence_compatible,
)
from .privacy import opaque_ref, redact_tree, safe_local_uri, sha256_file


INSPECTOR_VERSION = "ezviz-snapshot-v0.1.0"
TARGET_MODELS = {"CS-C6c-V101-1J4WF", "CS-EP-SDHY1"}
MODEL_KEYS = {"devicetype", "device_type", "devicemodel", "device_model", "model"}
SERIAL_KEYS = {"deviceserial", "device_serial", "serialnumber", "serial_number"}
ONLINE_KEYS = {"status", "onlinestatus", "online_status", "isonline", "is_online"}


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", key.replace("-", "_").lower())


def _walk(value: Any, prefix: str = "$") -> Iterable[tuple[str, Any]]:
    yield prefix, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{prefix}[{index}]")


def _value_for_keys(item: dict[str, Any], keys: set[str]) -> Any:
    for key, value in item.items():
        if _normalized_key(str(key)) in keys:
            return value
    return None


def _capability_fields(item: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in item.items():
        normalized = _normalized_key(str(key))
        if (
            "capabil" in normalized
            or normalized.startswith("support")
            or normalized
            in {
                "camera_num",
                "cameranum",
                "isencrypt",
                "is_encrypt",
                "channelcount",
            }
        ) and isinstance(value, (str, int, float, bool, type(None))):
            fields[str(key)] = value
    return fields


def inspect_ezviz_snapshot(
    path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
) -> EzvizSnapshotReport:
    ensure_source_evidence_compatible(source_type, evidence_level)
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    digest = sha256_file(path)
    sanitized, redacted_count = redact_tree(raw)

    device_dicts: list[dict[str, Any]] = []
    seen_identity: set[int] = set()
    for _, value in _walk(raw):
        if not isinstance(value, dict):
            continue
        model = _value_for_keys(value, MODEL_KEYS)
        serial = _value_for_keys(value, SERIAL_KEYS)
        if model is None and serial is None:
            continue
        if id(value) not in seen_identity:
            seen_identity.add(id(value))
            device_dicts.append(value)

    issues: list[QualityIssue] = []
    devices: list[DeviceSummary] = []
    ref_is_salted = True
    for index, item in enumerate(device_dicts):
        serial = _value_for_keys(item, SERIAL_KEYS)
        if serial is not None:
            device_ref, salted = opaque_ref("device", str(serial))
            ref_is_salted = ref_is_salted and salted
        else:
            device_ref = f"device_snapshot_index_{index}"
        model = _value_for_keys(item, MODEL_KEYS)
        online = _value_for_keys(item, ONLINE_KEYS)
        devices.append(
            DeviceSummary(
                device_ref=device_ref,
                model=str(model) if model is not None else None,
                online_status=online
                if isinstance(online, (str, int, bool)) or online is None
                else str(online),
                capability_fields=_capability_fields(item),
            )
        )

    if devices and not ref_is_salted:
        issues.append(
            QualityIssue(
                code="unsalted_device_ref",
                severity=Severity.WARNING,
                message="Set KANGSHIELD_REF_SALT before processing real device exports",
            )
        )
    if evidence_level in {EvidenceLevel.E0, EvidenceLevel.E1}:
        issues.append(
            QualityIssue(
                code="fixture_not_device_evidence",
                severity=Severity.WARNING,
                message="E0/E1 snapshots cannot prove target-device capability",
            )
        )

    capability_paths = sorted(
        {
            path_name
            for path_name, _ in _walk(sanitized)
            if "capabil" in path_name.lower() or "support" in path_name.lower()
        }
    )
    models_found = sorted({device.model for device in devices if device.model})
    target_models_found = sorted(TARGET_MODELS.intersection(models_found))
    checklist = {
        "device_list": "structure_observed" if devices else "not_observed",
        "online_status": "field_observed"
        if any(device.online_status is not None for device in devices)
        else "not_observed",
        "capability_set": "field_observed"
        if capability_paths or any(device.capability_fields for device in devices)
        else "not_observed",
        "live_preview": "requires_functional_test",
        "playback": "requires_functional_test",
        "capture": "requires_functional_test",
        "alarm": "requires_functional_test",
        "audio_track": "requires_media_probe",
        "sleep_fields": "requires_sleep_export",
    }
    asset = SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=Modality.DEVICE_SNAPSHOT,
        source_type=source_type,
        evidence_level=evidence_level,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
        metadata={
            "device_count_detected": len(devices),
            "raw_snapshot_persisted": False,
        },
    )
    return EzvizSnapshotReport(
        inspector_version=INSPECTOR_VERSION,
        asset=asset,
        devices=devices,
        models_found=models_found,
        target_models_found=target_models_found,
        capability_field_paths=capability_paths,
        sensitive_keys_redacted=redacted_count,
        sanitized_snapshot=sanitized,
        checklist=checklist,
        issues=issues,
    )
