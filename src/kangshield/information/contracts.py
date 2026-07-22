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
    LANGUAGE = "language"
    MULTIMODAL = "multimodal"
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
    privacy_level: PrivacyLevel = PrivacyLevel.DERIVED_SENSITIVE
    source_feature_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ModelBinding(ContractModel):
    task: str
    backend: str
    model_name: str
    model_version: str | None = None
    model_digest: str | None = None
    license: str
    device: str
    configuration: dict[str, Any] = Field(default_factory=dict)


class MultimodalWindow(ContractModel):
    schema_version: str = "1.0"
    window_id: str
    time_range: TimeRange
    video_observation_id: str
    audio_observation_id: str
    source_feature_refs: list[str] = Field(default_factory=list)
    pose_frame_count: int = Field(default=0, ge=0)
    max_person_count: int = Field(default=0, ge=0)
    track_ids: list[str] = Field(default_factory=list)
    speech_segment_count: int = Field(default=0, ge=0)
    transcript_feature_refs: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    stream_available: dict[str, bool] = Field(default_factory=dict)
    quality_status: QualityStatus = QualityStatus.UNKNOWN


class MultimodalPipelineReport(ContractModel):
    schema_version: str = "1.0"
    pipeline_version: str
    video_asset_id: str
    audio_asset_id: str
    model_bindings: list[ModelBinding]
    duration_ms: int = Field(ge=0)
    sampled_video_frames: int = Field(ge=0)
    pose_frames_with_people: int = Field(ge=0)
    pose_detection_count: int = Field(ge=0)
    speech_segment_count: int = Field(ge=0)
    transcript_segment_count: int = Field(ge=0)
    multimodal_window_count: int = Field(ge=0)
    semantic_tag_counts: dict[str, int] = Field(default_factory=dict)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class DatasetBenchmarkCase(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    pairing_kind: str
    video_path: str
    audio_path: str
    annotation_path: str
    video_dataset: str
    video_sequence: str
    video_class: str
    audio_dataset: str
    audio_sample: str
    audio_gender: str
    audio_duration_ms: int = Field(ge=0)
    reference_transcript: str
    limitations: list[str] = Field(default_factory=list)


class DatasetPhaseMetrics(ContractModel):
    sampled_frames: int = Field(ge=0)
    frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    tracked_frames: int = Field(ge=0)
    tracking_coverage: float = Field(ge=0.0, le=1.0)
    mean_pose_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_bbox_width_height_ratio: float | None = Field(default=None, ge=0.0)


class DatasetCaseEvaluation(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    run_id: str
    video_sequence: str
    video_class: str
    audio_sample: str
    audio_gender: str
    pairing_kind: str
    sampled_pose_frames: int = Field(ge=0)
    pose_frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    pose_frames_with_tracks: int = Field(ge=0)
    pose_tracking_coverage: float = Field(ge=0.0, le=1.0)
    unique_track_count: int = Field(ge=0)
    mean_pose_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    phase_metrics: dict[str, DatasetPhaseMetrics] = Field(default_factory=dict)
    maximum_annotation_match_error_ms: int = Field(ge=0)
    audio_duration_ms: int = Field(ge=0)
    speech_duration_ms: int = Field(ge=0)
    speech_coverage: float = Field(ge=0.0, le=1.0)
    reference_char_count: int = Field(ge=0)
    hypothesis_char_count: int = Field(ge=0)
    edit_distance: int = Field(ge=0)
    character_error_rate: float = Field(ge=0.0)
    transcript_exact_match: bool
    multimodal_window_count: int = Field(ge=0)
    processing_realtime_factor: float = Field(ge=0.0)
    limitations: list[str] = Field(default_factory=list)


class DatasetBenchmarkReport(ContractModel):
    schema_version: str = "1.0"
    benchmark_id: str
    benchmark_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    pairing_kind: str
    source_manifest_sha256: str = Field(min_length=64, max_length=64)
    benchmark_cases_sha256: str = Field(min_length=64, max_length=64)
    case_count: int = Field(ge=0)
    cases: list[DatasetCaseEvaluation]
    model_bindings: list[ModelBinding]
    total_reference_chars: int = Field(ge=0)
    total_edit_distance: int = Field(ge=0)
    corpus_character_error_rate: float = Field(ge=0.0)
    transcript_exact_match_count: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    pose_tracking_coverage: float = Field(ge=0.0, le=1.0)
    by_video_class: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    by_posture_phase: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class PoseBenchmarkCaseEvaluation(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    variant_id: str
    run_id: str
    video_sequence: str
    video_class: str
    sampled_frames: int = Field(ge=0)
    frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    tracked_frames: int = Field(ge=0)
    tracking_coverage: float = Field(ge=0.0, le=1.0)
    unique_track_count: int = Field(ge=0)
    mean_detection_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    mean_keypoint_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    mean_keypoint_visible_ratio_30: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    mean_keypoint_visible_ratio_50: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    phase_metrics: dict[str, DatasetPhaseMetrics] = Field(default_factory=dict)
    maximum_annotation_match_error_ms: int = Field(ge=0)
    evaluated_media_duration_ms: int = Field(ge=0)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class PoseBenchmarkVariantReport(ContractModel):
    schema_version: str = "1.0"
    variant_id: str
    model_bindings: list[ModelBinding]
    case_count: int = Field(ge=0)
    cases: list[PoseBenchmarkCaseEvaluation]
    sampled_frames: int = Field(ge=0)
    frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    tracked_frames: int = Field(ge=0)
    tracking_coverage: float = Field(ge=0.0, le=1.0)
    by_video_class: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    by_posture_phase: dict[str, dict[str, float | int]] = Field(
        default_factory=dict
    )
    quality_metrics: dict[str, float | int | None] = Field(default_factory=dict)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class PoseModelComparisonReport(ContractModel):
    schema_version: str = "1.0"
    benchmark_id: str
    benchmark_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    source_manifest_sha256: str = Field(min_length=64, max_length=64)
    benchmark_cases_sha256: str = Field(min_length=64, max_length=64)
    case_count: int = Field(ge=0)
    primary_metric: str
    variants: list[PoseBenchmarkVariantReport]
    comparisons: dict[str, dict[str, float | int | str | None]] = Field(
        default_factory=dict
    )
    limitations: list[str] = Field(default_factory=list)


class SpeechBenchmarkCaseEvaluation(ContractModel):
    """Privacy-safe per-case ASR metrics; transcript text is deliberately absent."""

    schema_version: str = "1.0"
    case_id: str
    variant_id: str
    run_id: str
    audio_sample: str
    audio_gender: str
    audio_duration_ms: int = Field(ge=0)
    segment_count: int = Field(ge=0)
    speech_duration_ms: int = Field(ge=0)
    speech_coverage: float = Field(ge=0.0, le=1.0)
    reference_char_count: int = Field(ge=0)
    hypothesis_char_count: int = Field(ge=0)
    edit_distance: int = Field(ge=0)
    character_error_rate: float = Field(ge=0.0)
    transcript_exact_match: bool
    blank_output: bool
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factor: float = Field(ge=0.0)
    limitations: list[str] = Field(default_factory=list)


class SpeechBenchmarkVariantReport(ContractModel):
    schema_version: str = "1.0"
    variant_id: str
    model_bindings: list[ModelBinding]
    case_count: int = Field(ge=0)
    cases: list[SpeechBenchmarkCaseEvaluation]
    total_audio_duration_ms: int = Field(ge=0)
    total_speech_duration_ms: int = Field(ge=0)
    speech_coverage: float = Field(ge=0.0, le=1.0)
    total_reference_chars: int = Field(ge=0)
    total_hypothesis_chars: int = Field(ge=0)
    total_edit_distance: int = Field(ge=0)
    corpus_character_error_rate: float = Field(ge=0.0)
    transcript_exact_match_count: int = Field(ge=0)
    blank_output_count: int = Field(ge=0)
    by_gender: dict[str, dict[str, float | int]] = Field(default_factory=dict)
    silence_probe: dict[str, float | int | bool | str | None] = Field(
        default_factory=dict
    )
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class SpeechModelComparisonReport(ContractModel):
    schema_version: str = "1.0"
    benchmark_id: str
    benchmark_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    source_manifest_sha256: str = Field(min_length=64, max_length=64)
    benchmark_cases_sha256: str = Field(min_length=64, max_length=64)
    case_count: int = Field(ge=0)
    primary_metric: str
    variants: list[SpeechBenchmarkVariantReport]
    comparisons: dict[str, dict[str, float | int | str | bool | None]] = Field(
        default_factory=dict
    )
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


class SleepFieldRouteAssessment(ContractModel):
    canonical_field: str
    monitoring_indicators: list[str] = Field(default_factory=list)
    priority: str
    route: str
    candidate_source_paths: list[str] = Field(default_factory=list)
    mapping_status: str | None = None
    status: str
    can_standardize: bool = False
    required_confirmations: list[str] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SleepDerivedRouteAssessment(ContractModel):
    indicator_id: str
    monitoring_indicators: list[str] = Field(default_factory=list)
    required_canonical_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    minimum_nights: int = Field(ge=1)
    status: str
    calculation_enabled: bool = False
    limitations: list[str] = Field(default_factory=list)


class SleepRouteAssessmentReport(ContractModel):
    schema_version: str = "1.0"
    route_version: str
    device_model: str
    evidence_level: EvidenceLevel
    profile_asset_id: str
    profile_asset_sha256: str = Field(min_length=64, max_length=64)
    policy_version: str
    policy_sha256: str = Field(min_length=64, max_length=64)
    policy_source_sha256: str = Field(min_length=64, max_length=64)
    mapping_config_sha256: str = Field(min_length=64, max_length=64)
    mapping_config_fixture_only: bool
    direct_fields: list[SleepFieldRouteAssessment]
    not_assumed_fields: list[SleepFieldRouteAssessment]
    derived_indicators: list[SleepDerivedRouteAssessment]
    counts: dict[str, int] = Field(default_factory=dict)
    decision: str
    values_persisted: bool = False
    issues: list[QualityIssue] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


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
