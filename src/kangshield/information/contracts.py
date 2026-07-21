from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceLevel(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


class Modality(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    SLEEP = "sleep"
    DEVICE_SNAPSHOT = "device_snapshot"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    LOCAL_FILE = "local_file"
    SDK_EXPORT = "sdk_export"
    API_RESPONSE = "api_response"
    FIXTURE = "fixture"


EVIDENCE_RANK = {
    EvidenceLevel.E0: 0,
    EvidenceLevel.E1: 1,
    EvidenceLevel.E2: 2,
    EvidenceLevel.E3: 3,
    EvidenceLevel.E4: 4,
}

MAX_EVIDENCE_BY_SOURCE = {
    SourceType.FIXTURE: EvidenceLevel.E1,
    SourceType.LOCAL_FILE: EvidenceLevel.E2,
    SourceType.SDK_EXPORT: EvidenceLevel.E2,
    SourceType.API_RESPONSE: EvidenceLevel.E3,
}


def ensure_source_evidence_compatible(
    source_type: SourceType,
    evidence_level: EvidenceLevel,
) -> None:
    maximum = MAX_EVIDENCE_BY_SOURCE[source_type]
    if EVIDENCE_RANK[evidence_level] > EVIDENCE_RANK[maximum]:
        raise ValueError(
            f"{source_type.value} input can provide at most {maximum.value} evidence; "
            f"received {evidence_level.value}"
        )


class PrivacyLevel(StrEnum):
    RAW_SENSITIVE = "raw_sensitive"
    DERIVED_SENSITIVE = "derived_sensitive"
    AGGREGATE = "aggregate"


class QualityStatus(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    UNKNOWN = "unknown"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TimeRange(ContractModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)


class SourceAsset(ContractModel):
    schema_version: str = "1.0"
    asset_id: str
    modality: Modality
    source_type: SourceType
    evidence_level: EvidenceLevel
    uri: str
    sha256: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0)
    captured_start_at: datetime | None = None
    captured_end_at: datetime | None = None
    ingested_at: datetime = Field(default_factory=utc_now)
    privacy_level: PrivacyLevel = PrivacyLevel.RAW_SENSITIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityIssue(ContractModel):
    code: str
    severity: Severity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Observation(ContractModel):
    schema_version: str = "1.0"
    observation_id: str
    asset_id: str
    elder_ref: str | None = None
    device_ref: str | None = None
    modality: Modality
    time_range: TimeRange = Field(default_factory=TimeRange)
    sequence: int = Field(default=0, ge=0)
    observed_at: datetime = Field(default_factory=utc_now)
    quality_status: QualityStatus = QualityStatus.UNKNOWN
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    missing_reasons: list[str] = Field(default_factory=list)
    payload_ref: str | None = None


class FeatureEvent(ContractModel):
    schema_version: str = "1.0"
    feature_id: str
    observation_id: str
    feature_type: str
    time_range: TimeRange = Field(default_factory=TimeRange)
    value: Any
    unit: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    quality: float | None = Field(default=None, ge=0.0, le=1.0)
    extractor_name: str
    extractor_version: str
    model_digest: str | None = None
    source_feature_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RunStep(ContractModel):
    name: str
    status: StepStatus = StepStatus.RUNNING
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None


class RunManifest(ContractModel):
    schema_version: str = "1.0"
    run_id: str
    stage: str
    status: RunStatus = RunStatus.RUNNING
    evidence_level: EvidenceLevel
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    code_version: str = "unknown"
    code_dirty: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)
    inputs: list[str] = Field(default_factory=list)
    steps: list[RunStep] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)


class MediaProbeReport(ContractModel):
    schema_version: str = "1.0"
    probe_version: str
    asset: SourceAsset
    observation: Observation
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
    issues: list[QualityIssue] = Field(default_factory=list)


class FieldStat(ContractModel):
    path: str
    types: list[str]
    present_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    sensitive: bool = False


class MappingCandidate(ContractModel):
    canonical_field: str
    source_path: str
    confidence: str
    requires_manual_confirmation: bool = True


class SleepProfileReport(ContractModel):
    schema_version: str = "1.0"
    profiler_version: str
    asset: SourceAsset
    observation: Observation
    container_path: str
    record_count: int = Field(ge=0)
    fields: list[FieldStat]
    mapping_candidates: list[MappingCandidate] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)


class DeviceSummary(ContractModel):
    device_ref: str
    model: str | None = None
    online_status: str | int | bool | None = None
    capability_fields: dict[str, Any] = Field(default_factory=dict)


class EzvizSnapshotReport(ContractModel):
    schema_version: str = "1.0"
    inspector_version: str
    asset: SourceAsset
    devices: list[DeviceSummary]
    models_found: list[str]
    target_models_found: list[str]
    capability_field_paths: list[str]
    sensitive_keys_redacted: int = Field(ge=0)
    sanitized_snapshot: Any
    checklist: dict[str, str]
    issues: list[QualityIssue] = Field(default_factory=list)
