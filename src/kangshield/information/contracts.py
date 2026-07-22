from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class FallFeatureConfig(ContractModel):
    schema_version: str = "1.0"
    feature_version: str = "fall-motion-features-v0.1.0"
    selection_strategy: Literal["largest_bbox"] = "largest_bbox"
    expected_keypoint_layout: Literal["COCO-17"] = "COCO-17"
    expected_keypoint_count: int = Field(default=17, ge=1)
    required_keypoint_indices: list[int] = Field(
        default_factory=lambda: [5, 6, 11, 12], min_length=1
    )
    keypoint_confidence_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0
    )
    keypoint_visible_ratio_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0
    )
    torso_horizontal_angle_max_deg: float = Field(
        default=45.0, ge=0.0, le=90.0
    )
    bbox_horizontal_ratio_threshold: float = Field(default=1.0, gt=0.0)
    descent_history_window_ms: int = Field(default=1000, gt=0)
    descent_min_span_ms: int = Field(default=600, gt=0)
    rapid_descent_center_y_ratio_threshold: float = Field(default=0.15, gt=0.0)
    stationary_window_ms: int = Field(default=600, gt=0)
    stationary_min_span_ms: int = Field(default=400, gt=0)
    stationary_center_displacement_diagonal_ratio_threshold: float = Field(
        default=0.03, gt=0.0
    )
    max_frame_gap_ms: int = Field(default=450, gt=0)
    maximum_annotation_match_error_ms: int = Field(default=120, ge=0)

    @model_validator(mode="after")
    def validate_windows_and_keypoints(self) -> "FallFeatureConfig":
        if self.expected_keypoint_count != 17:
            raise ValueError("COCO-17 layout requires exactly 17 keypoints")
        if len(self.required_keypoint_indices) != len(
            set(self.required_keypoint_indices)
        ):
            raise ValueError("required keypoint indices must be unique")
        if any(
            index < 0 or index >= self.expected_keypoint_count
            for index in self.required_keypoint_indices
        ):
            raise ValueError("required keypoint index is outside the expected layout")
        if self.required_keypoint_indices != [5, 6, 11, 12]:
            raise ValueError(
                "COCO-17 torso geometry requires shoulders 5/6 and hips 11/12"
            )
        if self.descent_min_span_ms > self.descent_history_window_ms:
            raise ValueError("descent minimum span cannot exceed its window")
        if self.stationary_min_span_ms > self.stationary_window_ms:
            raise ValueError("stationary minimum span cannot exceed its window")
        return self


class FallKeypointGate(ContractModel):
    expected_layout: str
    expected_count: int = Field(ge=1)
    observed_count: int = Field(ge=0)
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    visible_count: int = Field(ge=0)
    visible_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    visible_ratio_threshold: float = Field(ge=0.0, le=1.0)
    required_indices: list[int] = Field(default_factory=list)
    required_visible_count: int = Field(ge=0)
    required_all_visible: bool
    status: Literal[
        "passed",
        "failed_no_detection",
        "failed_layout",
        "failed_required_points",
        "failed_visible_ratio",
        "failed_degenerate_geometry",
    ]
    geometry_available: bool
    torso_angle_from_horizontal_deg: float | None = Field(
        default=None, ge=0.0, le=90.0
    )
    torso_horizontal_proxy: bool | None = None


class FallMotionFrameValue(ContractModel):
    schema_version: str = "1.0"
    feature_version: str
    frame_sequence: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    person_count: int = Field(ge=0)
    selection_strategy: Literal["largest_bbox"] = "largest_bbox"
    selected_detection_index: int | None = Field(default=None, ge=0)
    selected_track_id: int | None = None
    active_path: Literal["unavailable", "box_only", "box_plus_keypoints"]
    fallback_reasons: list[str] = Field(default_factory=list)
    bbox_width_height_ratio: float | None = Field(default=None, ge=0.0)
    bbox_center_x_ratio: float | None = None
    bbox_center_y_ratio: float | None = None
    bbox_bottom_y_ratio: float | None = None
    bbox_area_frame_ratio: float | None = Field(default=None, ge=0.0)
    bbox_horizontal_proxy: bool | None = None
    horizontal_duration_ms: int | None = Field(default=None, ge=0)
    descent_history_span_ms: int | None = Field(default=None, ge=0)
    center_drop_frame_height_ratio: float | None = None
    rapid_descent_proxy: bool | None = None
    stationary_history_span_ms: int | None = Field(default=None, ge=0)
    max_center_displacement_diagonal_ratio: float | None = Field(
        default=None, ge=0.0
    )
    low_motion_proxy: bool | None = None
    keypoint_gate: FallKeypointGate
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False


class FallCandidateTransitionRule(ContractModel):
    minimum_horizontal_duration_ms: int = Field(gt=0)
    rapid_descent_lookback_ms: int = Field(gt=0)
    low_motion_required: bool = False


class FallCandidateSettledRule(ContractModel):
    minimum_horizontal_duration_ms: int = Field(gt=0)
    low_motion_required: Literal[True] = True


class FallCandidateStateMachine(ContractModel):
    max_frame_gap_ms: int = Field(gt=0)
    release_grace_ms: int = Field(gt=0)
    refractory_ms: int = Field(ge=0)
    require_track_id: Literal[True] = True
    reset_on_track_change: Literal[True] = True
    transition_start_strategy: Literal[
        "earliest_recent_rapid_descent"
    ] = "earliest_recent_rapid_descent"
    settled_start_strategy: Literal[
        "horizontal_duration_backfill"
    ] = "horizontal_duration_backfill"


class FallEventCandidatePolicy(ContractModel):
    """Frozen policy that turns G4 frame proxies into deduplicated episodes."""

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=3)
    fixture: bool
    review_status: Literal[
        "fixture_only", "e1_exploratory_frozen"
    ] = "fixture_only"
    target_event_label: Literal["simulated_fall"] = "simulated_fall"
    input_fall_feature_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    input_fall_feature_version: str = "fall-motion-features-v0.1.0"
    candidate_representation: Literal[
        "deduplicated_event_episode"
    ] = "deduplicated_event_episode"
    candidate_event_version: str = "fall-event-candidate-v0.1.0"
    source_label_access: Literal[
        "forbidden_during_generation"
    ] = "forbidden_during_generation"
    transition_rule: FallCandidateTransitionRule | None = None
    settled_rule: FallCandidateSettledRule | None = None
    state_machine: FallCandidateStateMachine | None = None
    decision_logic_summary: str = Field(min_length=1)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_review_scope(self) -> "FallEventCandidatePolicy":
        rules = (self.transition_rule, self.settled_rule, self.state_machine)
        if self.fixture:
            if self.review_status != "fixture_only":
                raise ValueError("fixture candidate policy must remain fixture_only")
            if any(rule is not None for rule in rules) and any(
                rule is None for rule in rules
            ):
                raise ValueError("fixture candidate policy rules must be all or none")
        elif self.review_status != "e1_exploratory_frozen":
            raise ValueError("non-fixture candidate policy must be E1 frozen")
        elif any(rule is None for rule in rules):
            raise ValueError("non-fixture candidate policy requires all rules")
        if all(rule is None for rule in rules):
            return self
        assert self.transition_rule is not None
        assert self.settled_rule is not None
        if (
            self.transition_rule.minimum_horizontal_duration_ms
            > self.settled_rule.minimum_horizontal_duration_ms
        ):
            raise ValueError(
                "transition horizontal duration cannot exceed settled fallback"
            )
        return self


class FallEventCandidateEpisode(ContractModel):
    """Derived-sensitive candidate episode; it is not a risk or alert."""

    schema_version: Literal["1.0"] = "1.0"
    candidate_version: str
    candidate_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    detected_at_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    trigger_path: Literal[
        "rapid_descent_then_horizontal",
        "settled_horizontal_low_motion",
    ]
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False

    @model_validator(mode="after")
    def validate_window(self) -> "FallEventCandidateEpisode":
        if self.end_ms <= self.start_ms:
            raise ValueError("candidate episode end must be after start")
        if not self.start_ms <= self.detected_at_ms <= self.end_ms:
            raise ValueError("candidate detection must be inside the episode")
        return self


class FallFeatureMetrics(ContractModel):
    sampled_frames: int = Field(ge=0)
    unavailable_frames: int = Field(ge=0)
    box_available_frames: int = Field(ge=0)
    box_only_frames: int = Field(ge=0)
    box_plus_keypoints_frames: int = Field(ge=0)
    bbox_horizontal_frames: int = Field(ge=0)
    bbox_horizontal_rate: float = Field(ge=0.0, le=1.0)
    maximum_horizontal_duration_ms: int = Field(default=0, ge=0)
    descent_available_frames: int = Field(ge=0)
    rapid_descent_frames: int = Field(ge=0)
    rapid_descent_rate: float = Field(ge=0.0, le=1.0)
    stationary_available_frames: int = Field(ge=0)
    low_motion_frames: int = Field(ge=0)
    low_motion_rate: float = Field(ge=0.0, le=1.0)
    keypoint_gate_passed_frames: int = Field(ge=0)
    keypoint_gate_pass_rate: float = Field(ge=0.0, le=1.0)
    torso_horizontal_available_frames: int = Field(ge=0)
    torso_horizontal_frames: int = Field(ge=0)
    torso_horizontal_rate: float = Field(ge=0.0, le=1.0)
    fallback_reason_counts: dict[str, int] = Field(default_factory=dict)


class FallFeatureCaseEvaluation(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    variant_id: str
    video_sequence: str
    video_class: str
    source_pose_run_id: str
    source_pose_code_version: str
    source_pose_code_dirty: bool
    source_pose_manifest_sha256: str = Field(min_length=64, max_length=64)
    source_features_sha256: str = Field(min_length=64, max_length=64)
    annotation_sha256: str = Field(min_length=64, max_length=64)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    sampled_frames: int = Field(ge=0)
    maximum_annotation_match_error_ms: int = Field(ge=0)
    overall_metrics: FallFeatureMetrics
    phase_metrics: dict[str, FallFeatureMetrics] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


class FallFeatureBenchmarkReport(ContractModel):
    schema_version: str = "1.0"
    benchmark_id: str
    benchmark_version: str
    feature_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    benchmark_cases_sha256: str = Field(min_length=64, max_length=64)
    configuration_sha256: str = Field(min_length=64, max_length=64)
    source_pose_comparison_run_id: str
    source_pose_comparison_sha256: str = Field(min_length=64, max_length=64)
    source_pose_manifest_sha256: str = Field(min_length=64, max_length=64)
    source_pose_code_version: str
    source_pose_code_dirty: bool
    model_binding_policy_sha256: str = Field(min_length=64, max_length=64)
    source_binding_license_corrections: list[str] = Field(default_factory=list)
    variant_id: str
    model_bindings: list[ModelBinding]
    case_count: int = Field(ge=0)
    cases: list[FallFeatureCaseEvaluation]
    by_video_class: dict[str, FallFeatureMetrics] = Field(default_factory=dict)
    by_posture_phase: dict[str, FallFeatureMetrics] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


class FallAdlVideoCase(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    dataset_id: str
    dataset_version: int = Field(ge=1)
    video_path: str
    video_sha256: str = Field(min_length=64, max_length=64)
    video_byte_size: int = Field(gt=0)
    source_file_id: str
    subject_ref: str
    activity: Literal["pick_up_object", "sit_down", "kneel", "walk"]
    illumination_group: Literal[
        "natural_210_lux",
        "zero_lux_ir",
        "artificial_130_lux",
    ]
    approx_lux: int = Field(ge=0)
    expected_person_presence: Literal["present"] = "present"
    ground_truth_scope: Literal["dataset_action_level_no_fall"] = (
        "dataset_action_level_no_fall"
    )
    limitations: list[str] = Field(default_factory=list)


class FallAdlCaseEvaluation(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    variant_id: str
    run_id: str
    dataset_id: str
    activity: str
    illumination_group: str
    source_video_sha256: str = Field(min_length=64, max_length=64)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    sampled_frames: int = Field(ge=0)
    frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    tracked_frames: int = Field(ge=0)
    tracking_coverage: float = Field(ge=0.0, le=1.0)
    unique_track_count: int = Field(ge=0)
    evaluated_media_duration_ms: int = Field(ge=0)
    fall_feature_metrics: FallFeatureMetrics
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> "FallAdlCaseEvaluation":
        if self.frames_with_people > self.sampled_frames:
            raise ValueError("frames_with_people cannot exceed sampled_frames")
        if self.tracked_frames > self.frames_with_people:
            raise ValueError("tracked_frames cannot exceed frames_with_people")
        expected_pose = (
            round(self.frames_with_people / self.sampled_frames, 6)
            if self.sampled_frames
            else 0.0
        )
        expected_tracking = (
            round(self.tracked_frames / self.frames_with_people, 6)
            if self.frames_with_people
            else 0.0
        )
        if abs(self.pose_frame_coverage - expected_pose) > 1e-6:
            raise ValueError("pose_frame_coverage disagrees with frame counts")
        if abs(self.tracking_coverage - expected_tracking) > 1e-6:
            raise ValueError("tracking_coverage disagrees with frame counts")
        if self.fall_feature_metrics.sampled_frames != self.sampled_frames:
            raise ValueError("fall feature count disagrees with sampled_frames")
        return self


class FallAdlGroupMetrics(ContractModel):
    case_count: int = Field(ge=0)
    sampled_frames: int = Field(ge=0)
    frames_with_people: int = Field(ge=0)
    pose_frame_coverage: float = Field(ge=0.0, le=1.0)
    fall_feature_metrics: FallFeatureMetrics

    @model_validator(mode="after")
    def validate_counts(self) -> "FallAdlGroupMetrics":
        if self.frames_with_people > self.sampled_frames:
            raise ValueError("frames_with_people cannot exceed sampled_frames")
        expected = (
            round(self.frames_with_people / self.sampled_frames, 6)
            if self.sampled_frames
            else 0.0
        )
        if abs(self.pose_frame_coverage - expected) > 1e-6:
            raise ValueError("pose_frame_coverage disagrees with group counts")
        if self.fall_feature_metrics.sampled_frames != self.sampled_frames:
            raise ValueError("fall feature count disagrees with group sampled_frames")
        return self


class FallAdlVariantReport(ContractModel):
    schema_version: str = "1.0"
    variant_id: str
    model_bindings: list[ModelBinding]
    source_binding_license_corrections: list[str] = Field(default_factory=list)
    case_count: int = Field(ge=0)
    cases: list[FallAdlCaseEvaluation]
    overall: FallAdlGroupMetrics
    by_activity: dict[str, FallAdlGroupMetrics] = Field(default_factory=dict)
    by_illumination: dict[str, FallAdlGroupMetrics] = Field(default_factory=dict)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_count(self) -> "FallAdlVariantReport":
        if self.case_count != len(self.cases):
            raise ValueError("fall ADL variant case_count disagrees with cases")
        if self.overall.case_count != self.case_count:
            raise ValueError("fall ADL overall case_count disagrees with variant")
        if any(case.variant_id != self.variant_id for case in self.cases):
            raise ValueError("fall ADL case variant id disagrees with report")
        return self


class FallAdlBenchmarkReport(ContractModel):
    schema_version: str = "1.0"
    suite_id: str
    benchmark_version: str
    feature_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    suite_manifest_sha256: str = Field(min_length=64, max_length=64)
    configuration_sha256: str = Field(min_length=64, max_length=64)
    model_binding_policy_sha256: str = Field(min_length=64, max_length=64)
    pose_model_policy_sha256s: dict[str, str] = Field(default_factory=dict)
    dataset_id: str
    dataset_version: int = Field(ge=1)
    dataset_doi: str
    dataset_license: str
    case_count: int = Field(ge=0)
    variants: list[FallAdlVariantReport]
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_count(self) -> "FallAdlBenchmarkReport":
        if not self.variants:
            raise ValueError("fall ADL report must contain at least one variant")
        if any(variant.case_count != self.case_count for variant in self.variants):
            raise ValueError("fall ADL report case_count disagrees with a variant")
        if len({variant.variant_id for variant in self.variants}) != len(
            self.variants
        ):
            raise ValueError("fall ADL report variant ids must be unique")
        if any(
            len(digest) != 64
            for digest in self.pose_model_policy_sha256s.values()
        ):
            raise ValueError("fall ADL pose model policy digest is invalid")
        return self


class FallCandidateCaseStressEvaluation(ContractModel):
    """Timestamp-free public-data stress summary for one variant/case."""

    schema_version: Literal["1.0"] = "1.0"
    case_ref: str
    variant_id: str
    dataset_id: Literal["urfd", "caucafall-v4"]
    ground_truth_scope: Literal[
        "urfd_fall_video_class_with_phase_onset_proxy",
        "urfd_adl_video_class_no_fall",
        "caucafall_action_level_no_fall",
    ]
    scenario_group: str
    positive_case: bool
    duration_ms: int = Field(gt=0)
    input_frame_count: int = Field(gt=0)
    episode_count: int = Field(ge=0)
    activated: bool
    transition_trigger_count: int = Field(ge=0)
    settled_trigger_count: int = Field(ge=0)
    transition_onset_detection_delay_ms: int | None = None
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_counts(self) -> "FallCandidateCaseStressEvaluation":
        if self.episode_count != (
            self.transition_trigger_count + self.settled_trigger_count
        ):
            raise ValueError("candidate trigger counts disagree with episode count")
        if self.activated != (self.episode_count > 0):
            raise ValueError("candidate activation flag disagrees with episodes")
        expected_positive = self.ground_truth_scope == (
            "urfd_fall_video_class_with_phase_onset_proxy"
        )
        if self.positive_case != expected_positive:
            raise ValueError("candidate positive flag disagrees with label scope")
        if not self.positive_case and self.transition_onset_detection_delay_ms is not None:
            raise ValueError("negative case cannot carry a transition-onset delay")
        if self.positive_case and self.activated:
            if self.transition_onset_detection_delay_ms is None:
                raise ValueError("activated positive case requires an onset delay")
        elif self.transition_onset_detection_delay_ms is not None:
            raise ValueError("non-activated case cannot carry an onset delay")
        return self


class FallCandidateVariantStressReport(ContractModel):
    """Aggregate-only candidate stress evidence for one pose variant."""

    schema_version: Literal["1.0"] = "1.0"
    variant_id: str
    source_urfd_run_id: str
    source_urfd_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_urfd_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_urfd_features_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_caucafall_run_id: str
    model_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_generator_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    case_count: int = Field(ge=0)
    urfd_fall_case_count: int = Field(ge=0)
    urfd_fall_activated_count: int = Field(ge=0)
    urfd_adl_negative_case_count: int = Field(ge=0)
    urfd_adl_false_activation_count: int = Field(ge=0)
    caucafall_negative_case_count: int = Field(ge=0)
    caucafall_false_activation_count: int = Field(ge=0)
    negative_exposure_ms: int = Field(ge=0)
    negative_episode_count: int = Field(ge=0)
    false_activations_per_hour: float = Field(ge=0.0)
    episode_count: int = Field(ge=0)
    transition_trigger_count: int = Field(ge=0)
    settled_trigger_count: int = Field(ge=0)
    detection_delay_count: int = Field(ge=0)
    mean_transition_onset_detection_delay_ms: float | None = None
    median_transition_onset_detection_delay_ms: float | None = None
    minimum_transition_onset_detection_delay_ms: int | None = None
    maximum_transition_onset_detection_delay_ms: int | None = None
    cases: list[FallCandidateCaseStressEvaluation]
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aggregates(self) -> "FallCandidateVariantStressReport":
        if self.case_count != len(self.cases):
            raise ValueError("candidate variant case count disagrees with cases")
        if any(case.variant_id != self.variant_id for case in self.cases):
            raise ValueError("candidate case variant disagrees with parent")
        urfd_fall = [case for case in self.cases if case.positive_case]
        urfd_adl = [
            case
            for case in self.cases
            if case.ground_truth_scope == "urfd_adl_video_class_no_fall"
        ]
        caucafall = [
            case
            for case in self.cases
            if case.ground_truth_scope == "caucafall_action_level_no_fall"
        ]
        negatives = [case for case in self.cases if not case.positive_case]
        expected = {
            "urfd_fall_case_count": len(urfd_fall),
            "urfd_fall_activated_count": sum(case.activated for case in urfd_fall),
            "urfd_adl_negative_case_count": len(urfd_adl),
            "urfd_adl_false_activation_count": sum(
                case.activated for case in urfd_adl
            ),
            "caucafall_negative_case_count": len(caucafall),
            "caucafall_false_activation_count": sum(
                case.activated for case in caucafall
            ),
            "negative_exposure_ms": sum(case.duration_ms for case in negatives),
            "negative_episode_count": sum(case.episode_count for case in negatives),
            "episode_count": sum(case.episode_count for case in self.cases),
            "transition_trigger_count": sum(
                case.transition_trigger_count for case in self.cases
            ),
            "settled_trigger_count": sum(
                case.settled_trigger_count for case in self.cases
            ),
            "detection_delay_count": sum(
                case.transition_onset_detection_delay_ms is not None
                for case in self.cases
            ),
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise ValueError(f"candidate variant {field} disagrees with cases")
        expected_rate = (
            round(self.negative_episode_count * 3_600_000 / self.negative_exposure_ms, 6)
            if self.negative_exposure_ms
            else 0.0
        )
        if abs(self.false_activations_per_hour - expected_rate) > 1e-6:
            raise ValueError("candidate false activations/hour disagrees with exposure")
        delays = [
            case.transition_onset_detection_delay_ms
            for case in self.cases
            if case.transition_onset_detection_delay_ms is not None
        ]
        summary_values = (
            self.mean_transition_onset_detection_delay_ms,
            self.median_transition_onset_detection_delay_ms,
            self.minimum_transition_onset_detection_delay_ms,
            self.maximum_transition_onset_detection_delay_ms,
        )
        if not delays and any(value is not None for value in summary_values):
            raise ValueError("empty delay set cannot carry delay summaries")
        if delays and any(value is None for value in summary_values):
            raise ValueError("non-empty delay set requires all delay summaries")
        if delays:
            ordered = sorted(delays)
            midpoint = len(ordered) // 2
            expected_median = (
                float(ordered[midpoint])
                if len(ordered) % 2
                else (ordered[midpoint - 1] + ordered[midpoint]) / 2
            )
            expected_delay_summary = {
                "mean_transition_onset_detection_delay_ms": round(
                    sum(ordered) / len(ordered), 3
                ),
                "median_transition_onset_detection_delay_ms": round(
                    expected_median, 3
                ),
                "minimum_transition_onset_detection_delay_ms": ordered[0],
                "maximum_transition_onset_detection_delay_ms": ordered[-1],
            }
            for field, expected_value in expected_delay_summary.items():
                if getattr(self, field) != expected_value:
                    raise ValueError(
                        f"candidate variant {field} disagrees with cases"
                    )
        return self


class FallCandidatePublicStressReport(ContractModel):
    """E1 public-data stress report; it is not held-out event validation."""

    schema_version: Literal["1.0"] = "1.0"
    benchmark_id: str
    benchmark_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    candidate_policy_id: str
    candidate_generator_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    urfd_benchmark_id: str
    urfd_benchmark_cases_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    caucafall_suite_id: str
    caucafall_suite_manifest_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    source_caucafall_run_id: str
    source_caucafall_manifest_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    source_caucafall_report_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    variant_count: int = Field(ge=0)
    case_evaluation_count: int = Field(ge=0)
    variants: list[FallCandidateVariantStressReport]
    raw_paths_persisted: Literal[False] = False
    candidate_windows_persisted_in_report: Literal[False] = False
    candidate_episode_artifact_scope: Literal[
        "derived_sensitive_run_feature_events"
    ] = "derived_sensitive_run_feature_events"
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_variants(self) -> "FallCandidatePublicStressReport":
        if self.evidence_level is not EvidenceLevel.E1:
            raise ValueError("public candidate stress report must remain E1")
        if self.variant_count != len(self.variants) or not self.variants:
            raise ValueError("candidate report variant count disagrees")
        ids = [variant.variant_id for variant in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate report variant ids must be unique")
        if self.case_evaluation_count != sum(
            variant.case_count for variant in self.variants
        ):
            raise ValueError("candidate report case evaluation count disagrees")
        if any(
            variant.fall_feature_policy_sha256
            != self.fall_feature_policy_sha256
            or variant.candidate_generator_policy_sha256
            != self.candidate_generator_policy_sha256
            or variant.source_caucafall_run_id
            != self.source_caucafall_run_id
            for variant in self.variants
        ):
            raise ValueError("candidate report source policy binding disagrees")
        return self


class FallFeatureClipStream(ContractModel):
    """One capture clip's derived-sensitive G4 frame stream."""

    scenario_id: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    observation_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    frame_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_relative_path(self) -> "FallFeatureClipStream":
        parts = self.relative_path.split("/")
        if (
            self.relative_path.startswith("/")
            or "\\" in self.relative_path
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("fall feature clip path must be normalized and relative")
        return self


class FallFeatureCaptureSet(ContractModel):
    """Capture-bound index produced by a generic G4 feature run."""

    schema_version: Literal["1.0"] = "1.0"
    feature_set_id: str = Field(min_length=3)
    fixture: bool
    evidence_level: EvidenceLevel
    variant_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    capture_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_version: str = Field(min_length=1)
    generated_at: datetime
    labels_read_during_generation: Literal[False] = False
    clip_count: int = Field(ge=1)
    clips: list[FallFeatureClipStream] = Field(min_length=1)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_feature_set(self) -> "FallFeatureCaptureSet":
        if self.generated_at.utcoffset() is None:
            raise ValueError("fall feature set generated_at requires a timezone")
        if self.fixture and self.evidence_level is not EvidenceLevel.E1:
            raise ValueError("fixture fall feature set must remain E1")
        if self.clip_count != len(self.clips):
            raise ValueError("fall feature set clip count disagrees")
        for values, label in (
            ([clip.scenario_id for clip in self.clips], "scenario ids"),
            ([clip.relative_path for clip in self.clips], "paths"),
            ([clip.observation_id for clip in self.clips], "observation ids"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"fall feature set {label} must be unique")
        return self


class FallFeatureCaptureClipReport(ContractModel):
    """Aggregate producer facts for one held-out capture clip."""

    clip_ref: str
    scenario_id: str
    duration_ms: int = Field(gt=0)
    sampled_frames: int = Field(gt=0)
    frames_with_people: int = Field(ge=0)
    tracked_frames: int = Field(ge=0)
    unique_track_count: int = Field(ge=0)
    fall_feature_metrics: FallFeatureMetrics
    timing_ms: dict[str, float] = Field(default_factory=dict)
    realtime_factors: dict[str, float] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_frame_counts(self) -> "FallFeatureCaptureClipReport":
        if self.frames_with_people > self.sampled_frames:
            raise ValueError("capture frames with people exceed sampled frames")
        if self.tracked_frames > self.frames_with_people:
            raise ValueError("capture tracked frames exceed frames with people")
        if self.fall_feature_metrics.sampled_frames != self.sampled_frames:
            raise ValueError("capture fall-feature frame count disagrees")
        return self


class FallFeatureCaptureReport(ContractModel):
    """Privacy-safe report for a capture-bound pose-to-G4 producer run."""

    schema_version: Literal["1.0"] = "1.0"
    producer_version: str
    source_run_id: str
    fixture: bool
    evidence_level: EvidenceLevel
    capture_ref: str
    capture_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_readiness_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_assessment_run_id: str
    capture_assessment_run_manifest_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    variant_id: str
    model_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_version: str
    sample_fps: float = Field(gt=0.0)
    model_bindings: list[ModelBinding] = Field(min_length=1)
    model_binding_license_corrections: list[str] = Field(default_factory=list)
    clip_count: int = Field(ge=1)
    input_frame_count: int = Field(ge=1)
    clips: list[FallFeatureCaptureClipReport] = Field(min_length=1)
    model_load_ms: float = Field(ge=0.0)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    raw_media_copied: Literal[False] = False
    raw_pose_events_persisted_in_run: Literal[True] = True
    labels_read_during_generation: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_capture_report(self) -> "FallFeatureCaptureReport":
        if self.fixture and self.evidence_level is not EvidenceLevel.E1:
            raise ValueError("fixture fall-feature capture report must remain E1")
        if self.clip_count != len(self.clips):
            raise ValueError("fall-feature capture clip count disagrees")
        if self.input_frame_count != sum(
            clip.sampled_frames for clip in self.clips
        ):
            raise ValueError("fall-feature capture frame count disagrees")
        values = [clip.scenario_id for clip in self.clips]
        if len(values) != len(set(values)):
            raise ValueError("fall-feature capture scenario ids must be unique")
        return self


class FallCandidatePredictionEvent(ContractModel):
    candidate_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    detected_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_candidate(self) -> "FallCandidatePredictionEvent":
        if self.end_ms <= self.start_ms:
            raise ValueError("candidate event end must be after start")
        if not self.start_ms <= self.detected_at_ms <= self.end_ms:
            raise ValueError("candidate detection time must be inside its episode")
        return self


class FallCandidatePredictionClip(ContractModel):
    scenario_id: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    candidates: list[FallCandidatePredictionEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidates(self) -> "FallCandidatePredictionClip":
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique within a clip")
        if any(candidate.end_ms > self.duration_ms for candidate in self.candidates):
            raise ValueError("candidate event exceeds clip duration")
        ordered = sorted(
            (candidate.start_ms, candidate.end_ms)
            for candidate in self.candidates
        )
        if any(
            next_start < current_end
            for (_, current_end), (next_start, _) in zip(
                ordered,
                ordered[1:],
                strict=False,
            )
        ):
            raise ValueError("deduplicated candidate episodes cannot overlap")
        return self


class FallCandidatePredictionSet(ContractModel):
    """Exact candidate stream consumed by the held-out event evaluator."""

    schema_version: Literal["1.0"] = "1.0"
    prediction_set_id: str = Field(min_length=3)
    variant_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    capture_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_generator_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    generated_at: datetime
    clips: list[FallCandidatePredictionClip] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prediction_set(self) -> "FallCandidatePredictionSet":
        if self.generated_at.utcoffset() is None:
            raise ValueError("prediction generated_at requires a timezone")
        ids = [clip.scenario_id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("prediction scenario ids must be unique")
        return self


class FallCandidateExportSummary(ContractModel):
    """Timestamp-free summary for one capture-bound candidate source run."""

    schema_version: Literal["1.0"] = "1.0"
    exporter_version: str
    fixture: bool
    evidence_level: EvidenceLevel
    capture_ref: str
    variant_id: str
    source_feature_run_id: str
    source_feature_run_manifest_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    source_feature_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_generator_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    candidate_events_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clip_count: int = Field(ge=1)
    input_frame_count: int = Field(ge=1)
    activated_clip_count: int = Field(ge=0)
    candidate_episode_count: int = Field(ge=0)
    transition_trigger_count: int = Field(ge=0)
    settled_trigger_count: int = Field(ge=0)
    source_paths_persisted: Literal[False] = False
    candidate_windows_persisted_in_summary: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> "FallCandidateExportSummary":
        if self.activated_clip_count > self.clip_count:
            raise ValueError("activated clip count exceeds clip count")
        if self.candidate_episode_count != (
            self.transition_trigger_count + self.settled_trigger_count
        ):
            raise ValueError("candidate export trigger counts disagree")
        if self.candidate_episode_count < self.activated_clip_count:
            raise ValueError("candidate count is below activated clip count")
        return self


class StaticPersonBox(ContractModel):
    bbox_norm_xyxy: list[float] = Field(min_length=4, max_length=4)
    is_occluded: bool = False
    is_truncated: bool = False

    @model_validator(mode="after")
    def validate_box(self) -> "StaticPersonBox":
        x1, y1, x2, y2 = self.bbox_norm_xyxy
        if any(value < 0.0 or value > 1.0 for value in self.bbox_norm_xyxy):
            raise ValueError("normalized person box coordinates must be in [0, 1]")
        if x2 <= x1 or y2 <= y1:
            raise ValueError("normalized person box must have positive area")
        return self


class StaticHomeImageCase(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    dataset_id: str
    dataset_version: int = Field(ge=1)
    split: Literal["validation"] = "validation"
    image_id: str
    image_path: str
    image_sha256: str = Field(min_length=64, max_length=64)
    image_byte_size: int = Field(gt=0)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    scenario: Literal[
        "person_absent_furniture",
        "person_absent_pet",
        "multi_person_indoor",
    ]
    expected_person_presence: Literal["absent", "present"]
    expected_person_count: int = Field(ge=0)
    person_boxes: list[StaticPersonBox] = Field(default_factory=list)
    context_labels: list[str] = Field(default_factory=list)
    image_license: Literal["CC-BY-2.0"] = "CC-BY-2.0"
    manual_review_status: Literal["passed"] = "passed"
    ground_truth_scope: Literal[
        "openimages_verified_person_label_and_validation_person_boxes"
    ] = "openimages_verified_person_label_and_validation_person_boxes"
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_person_contract(self) -> "StaticHomeImageCase":
        if self.expected_person_count != len(self.person_boxes):
            raise ValueError("expected person count disagrees with person boxes")
        if self.scenario.startswith("person_absent"):
            if self.expected_person_presence != "absent" or self.person_boxes:
                raise ValueError("person-absent case cannot contain person boxes")
        elif (
            self.expected_person_presence != "present"
            or self.expected_person_count < 2
        ):
            raise ValueError("multi-person case must contain at least two people")
        if not self.context_labels:
            raise ValueError("static home case requires context labels")
        return self


class StaticHomeCaseEvaluation(ContractModel):
    schema_version: str = "1.0"
    case_id: str
    variant_id: str
    run_id: str
    scenario: str
    source_image_sha256: str = Field(min_length=64, max_length=64)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    ground_truth_person_count: int = Field(ge=0)
    predicted_person_count: int = Field(ge=0)
    matched_person_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    person_activation: bool
    mean_detection_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    mean_matched_iou: float | None = Field(default=None, ge=0.0, le=1.0)
    inference_ms: float = Field(ge=0.0)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> "StaticHomeCaseEvaluation":
        if self.matched_person_count > min(
            self.ground_truth_person_count, self.predicted_person_count
        ):
            raise ValueError("matched person count exceeds available boxes")
        if self.false_positive_count != (
            self.predicted_person_count - self.matched_person_count
        ):
            raise ValueError("static false-positive count is inconsistent")
        if self.false_negative_count != (
            self.ground_truth_person_count - self.matched_person_count
        ):
            raise ValueError("static false-negative count is inconsistent")
        if self.person_activation != (self.predicted_person_count > 0):
            raise ValueError("person activation disagrees with predictions")
        if self.matched_person_count == 0 and self.mean_matched_iou is not None:
            raise ValueError("matched IoU requires at least one match")
        return self


class StaticHomeGroupMetrics(ContractModel):
    case_count: int = Field(ge=0)
    ground_truth_person_count: int = Field(ge=0)
    predicted_person_count: int = Field(ge=0)
    matched_person_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    detection_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    detection_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    person_absent_case_count: int = Field(ge=0)
    person_absent_false_activation_cases: int = Field(ge=0)
    person_absent_false_activation_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    multi_person_case_count: int = Field(ge=0)
    multi_any_person_detected_cases: int = Field(ge=0)
    multi_all_people_matched_cases: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_metrics(self) -> "StaticHomeGroupMetrics":
        expected_precision = (
            round(self.matched_person_count / self.predicted_person_count, 6)
            if self.predicted_person_count
            else None
        )
        expected_recall = (
            round(self.matched_person_count / self.ground_truth_person_count, 6)
            if self.ground_truth_person_count
            else None
        )
        expected_false_activation = (
            round(
                self.person_absent_false_activation_cases
                / self.person_absent_case_count,
                6,
            )
            if self.person_absent_case_count
            else None
        )
        if self.detection_precision != expected_precision:
            raise ValueError("static detection precision is inconsistent")
        if self.detection_recall != expected_recall:
            raise ValueError("static detection recall is inconsistent")
        if self.person_absent_false_activation_rate != expected_false_activation:
            raise ValueError("static false-activation rate is inconsistent")
        if self.person_absent_false_activation_cases > self.person_absent_case_count:
            raise ValueError("static false-activation cases exceed absent cases")
        if self.multi_any_person_detected_cases > self.multi_person_case_count:
            raise ValueError("multi-person detected cases exceed multi-person cases")
        if self.multi_all_people_matched_cases > self.multi_person_case_count:
            raise ValueError("multi-person complete cases exceed multi-person cases")
        return self


class StaticHomeVariantReport(ContractModel):
    schema_version: str = "1.0"
    variant_id: str
    model_bindings: list[ModelBinding]
    source_binding_license_corrections: list[str] = Field(default_factory=list)
    case_count: int = Field(ge=0)
    cases: list[StaticHomeCaseEvaluation]
    overall: StaticHomeGroupMetrics
    by_scenario: dict[str, StaticHomeGroupMetrics] = Field(default_factory=dict)
    runtime_environment: dict[str, Any] = Field(default_factory=dict)
    timing_ms: dict[str, float] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_count(self) -> "StaticHomeVariantReport":
        if self.case_count != len(self.cases):
            raise ValueError("static variant case count disagrees with cases")
        if self.overall.case_count != self.case_count:
            raise ValueError("static overall case count disagrees with variant")
        if any(case.variant_id != self.variant_id for case in self.cases):
            raise ValueError("static case variant id disagrees with report")
        return self


class StaticHomeBenchmarkReport(ContractModel):
    schema_version: str = "1.0"
    suite_id: str
    benchmark_version: str
    evidence_level: EvidenceLevel = EvidenceLevel.E1
    suite_manifest_sha256: str = Field(min_length=64, max_length=64)
    source_manifest_sha256: str = Field(min_length=64, max_length=64)
    model_binding_policy_sha256: str = Field(min_length=64, max_length=64)
    pose_model_policy_sha256s: dict[str, str] = Field(default_factory=dict)
    dataset_id: str
    dataset_version: int = Field(ge=1)
    annotation_license: str
    required_image_license: str
    matching_iou_threshold: float = Field(ge=0.0, le=1.0)
    case_count: int = Field(ge=0)
    variants: list[StaticHomeVariantReport]
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_count(self) -> "StaticHomeBenchmarkReport":
        if not self.variants:
            raise ValueError("static report must contain at least one variant")
        if any(variant.case_count != self.case_count for variant in self.variants):
            raise ValueError("static variant case count disagrees with report")
        return self


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


class MediaStreamTiming(ContractModel):
    stream_index: int = Field(ge=0)
    stream_type: Literal["video", "audio"]
    codec_name: str | None = None
    time_base: str | None = None
    declared_start_pts: int | None = None
    declared_start_ms: float | None = None
    declared_duration_pts: int | None = None
    declared_duration_ms: float | None = None
    declared_frame_count: int | None = Field(default=None, ge=0)
    packet_count: int = Field(ge=0)
    packets_with_pts: int = Field(ge=0)
    packets_with_dts: int = Field(ge=0)
    missing_pts_count: int = Field(ge=0)
    missing_dts_count: int = Field(ge=0)
    negative_pts_count: int = Field(ge=0)
    pts_backward_step_count: int = Field(ge=0)
    dts_backward_step_count: int = Field(ge=0)
    first_demux_pts: int | None = None
    last_demux_pts: int | None = None
    min_pts: int | None = None
    max_pts: int | None = None
    min_pts_ms: float | None = None
    max_pts_ms: float | None = None
    end_pts_ms: float | None = None
    pts_span_ms: float | None = None
    packet_duration_sum_ms: float | None = None
    median_forward_pts_step_ms: float | None = None
    max_forward_pts_step_ms: float | None = None
    scan_truncated: bool = False
    technical_metadata: dict[str, Any] = Field(default_factory=dict)


class ContainerTimingReport(ContractModel):
    schema_version: str = "1.0"
    timing_version: str
    backend: Literal["pyav"] = "pyav"
    backend_version: str
    format_names: list[str] = Field(default_factory=list)
    container_start_ms: float | None = None
    container_duration_ms: float | None = None
    container_bit_rate: int | None = Field(default=None, ge=0)
    metadata_key_count: int = Field(ge=0)
    metadata_values_persisted: bool = False
    source_path_persisted: bool = False
    stream_count: int = Field(ge=0)
    video_stream_count: int = Field(ge=0)
    audio_stream_count: int = Field(ge=0)
    video_track_status: Literal["present", "absent"]
    audio_track_status: Literal["present", "absent"]
    same_container_av: bool
    can_measure_start_offset: bool
    audio_minus_video_start_ms: float | None = None
    audio_minus_video_end_ms: float | None = None
    duration_delta_ms: float | None = None
    drift_estimate_available: bool = False
    packet_scan_limit_per_stream: int = Field(gt=0)
    streams: list[MediaStreamTiming] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MediaProbeReport(ContractModel):
    schema_version: str = "1.0"
    probe_version: str
    asset: SourceAsset
    observation: Observation
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
    container_timing: ContainerTimingReport | None = None
    issues: list[QualityIssue] = Field(default_factory=list)


class M2cClipReadiness(ContractModel):
    """Privacy-safe result for one C6c capture clip."""

    clip_ref: str
    scenario_id: str
    media_asset_id: str | None = None
    manifest_digest_match: bool = False
    manifest_byte_size_match: bool = False
    probe_quality_status: QualityStatus = QualityStatus.UNKNOWN
    video_track_status: str = "unknown"
    audio_track_status: str = "unknown"
    annotation_labels: list[str] = Field(default_factory=list)
    annotation_window_count: int = Field(ge=0)
    synchronization_event_count: int = Field(ge=0)
    synchronization_offset_start_ms: float | None = None
    synchronization_offset_end_ms: float | None = None
    synchronization_drift_ms_per_minute: float | None = None
    structurally_usable: bool = False
    issues: list[QualityIssue] = Field(default_factory=list)


class M2cCaptureReadinessReport(ContractModel):
    """Aggregate-only M2c gate; raw paths, refs and label windows are excluded."""

    schema_version: str = "1.0"
    assessor_version: str
    capture_ref: str
    evidence_level: EvidenceLevel
    source_type: SourceType
    manifest_asset_id: str
    manifest_sha256: str = Field(min_length=64, max_length=64)
    policy_version: str
    policy_sha256: str = Field(min_length=64, max_length=64)
    template_only: bool
    synthetic: bool
    clips: list[M2cClipReadiness]
    counts: dict[str, int] = Field(default_factory=dict)
    coverage: dict[str, list[str] | int | bool] = Field(default_factory=dict)
    held_out_checks: dict[str, bool | int] = Field(default_factory=dict)
    camera_ready_for_model_retest: bool = False
    camera_matrix_complete: bool = False
    sleep_sample_ready_for_profiling: bool = False
    capture_bundle_ready_for_review: bool = False
    decision: str
    quality_status: QualityStatus
    raw_paths_persisted: Literal[False] = False
    identity_refs_persisted: Literal[False] = False
    annotation_windows_persisted: Literal[False] = False
    health_values_persisted: Literal[False] = False
    issues: list[QualityIssue] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FallEventAnnotationAgreement(ContractModel):
    """Aggregate-only agreement for one independent annotator pair."""

    schema_version: str = "1.0"
    pair_ref: str
    compared_label_count: int = Field(ge=1)
    left_window_count: int = Field(ge=0)
    right_window_count: int = Field(ge=0)
    matched_window_count: int = Field(ge=0)
    unmatched_window_count: int = Field(ge=0)
    interval_f1: float = Field(ge=0.0, le=1.0)
    target_left_window_count: int = Field(ge=0)
    target_right_window_count: int = Field(ge=0)
    target_matched_window_count: int = Field(ge=0)
    target_unmatched_window_count: int = Field(ge=0)
    target_interval_f1: float = Field(ge=0.0, le=1.0)
    matched_target_onset_count: int = Field(ge=0)
    mean_absolute_target_onset_difference_ms: float | None = Field(
        default=None,
        ge=0.0,
    )
    maximum_absolute_target_onset_difference_ms: float | None = Field(
        default=None,
        ge=0.0,
    )
    passes: bool


class FallEventCaseEvaluation(ContractModel):
    """Privacy-safe event counts for one held-out clip."""

    schema_version: str = "1.0"
    case_ref: str
    scenario_id: str
    scenario: str
    duration_ms: int = Field(gt=0)
    ground_truth_event_count: int = Field(ge=0)
    candidate_event_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    negative_case: bool
    false_activation: bool
    detection_delay_count: int = Field(ge=0)
    mean_detection_delay_ms: float | None = None
    median_detection_delay_ms: float | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "FallEventCaseEvaluation":
        if self.true_positive_count + self.false_positive_count != (
            self.candidate_event_count
        ):
            raise ValueError("candidate event accounting is inconsistent")
        if self.true_positive_count + self.false_negative_count != (
            self.ground_truth_event_count
        ):
            raise ValueError("ground-truth event accounting is inconsistent")
        if self.detection_delay_count != self.true_positive_count:
            raise ValueError("detection-delay count must equal true positives")
        if self.negative_case != (self.ground_truth_event_count == 0):
            raise ValueError("negative-case flag disagrees with ground truth")
        if self.false_activation != (
            self.negative_case and self.candidate_event_count > 0
        ):
            raise ValueError("false-activation flag disagrees with event counts")
        return self


class FallEventVariantEvaluation(ContractModel):
    """One candidate-event stream scored against adjudicated intervals."""

    schema_version: str = "1.0"
    variant_id: str
    source_run_id: str
    source_code_version: str
    source_evidence_level: EvidenceLevel
    source_run_completed: bool
    source_run_clean: bool
    model_policy_sha256: str = Field(min_length=64, max_length=64)
    fall_feature_policy_sha256: str = Field(min_length=64, max_length=64)
    candidate_generator_policy_sha256: str = Field(min_length=64, max_length=64)
    clip_count: int = Field(ge=0)
    exposure_ms: int = Field(ge=0)
    ground_truth_event_count: int = Field(ge=0)
    candidate_event_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    false_activations_per_hour: float = Field(ge=0.0)
    negative_clip_count: int = Field(ge=0)
    false_activation_clip_count: int = Field(ge=0)
    negative_clip_false_activation_rate: float = Field(ge=0.0, le=1.0)
    detection_delay_count: int = Field(ge=0)
    mean_detection_delay_ms: float | None = None
    median_detection_delay_ms: float | None = None
    p95_detection_delay_ms: float | None = None
    minimum_detection_delay_ms: float | None = None
    maximum_detection_delay_ms: float | None = None
    cases: list[FallEventCaseEvaluation]
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_aggregates(self) -> "FallEventVariantEvaluation":
        if len(self.cases) != self.clip_count:
            raise ValueError("event variant clip count disagrees with cases")
        sums = {
            "exposure_ms": sum(case.duration_ms for case in self.cases),
            "ground_truth_event_count": sum(
                case.ground_truth_event_count for case in self.cases
            ),
            "candidate_event_count": sum(
                case.candidate_event_count for case in self.cases
            ),
            "true_positive_count": sum(
                case.true_positive_count for case in self.cases
            ),
            "false_positive_count": sum(
                case.false_positive_count for case in self.cases
            ),
            "false_negative_count": sum(
                case.false_negative_count for case in self.cases
            ),
            "negative_clip_count": sum(case.negative_case for case in self.cases),
            "false_activation_clip_count": sum(
                case.false_activation for case in self.cases
            ),
            "detection_delay_count": sum(
                case.detection_delay_count for case in self.cases
            ),
        }
        for field, expected in sums.items():
            if getattr(self, field) != expected:
                raise ValueError(f"event variant {field} disagrees with cases")
        return self


class FallEventEvaluationReadinessReport(ContractModel):
    """Aggregate-only G4 event evaluation and readiness result."""

    schema_version: str = "1.0"
    assessor_version: str
    evaluation_ref: str
    evidence_level: EvidenceLevel
    source_type: SourceType
    bundle_sha256: str = Field(min_length=64, max_length=64)
    policy_version: str
    policy_sha256: str = Field(min_length=64, max_length=64)
    capture_ref: str
    capture_manifest_sha256: str = Field(min_length=64, max_length=64)
    capture_readiness_sha256: str = Field(min_length=64, max_length=64)
    candidate_generator_policy_sha256: str = Field(min_length=64, max_length=64)
    template_only: bool
    synthetic: bool
    fixture: bool
    target_event_label: Literal["simulated_fall"] = "simulated_fall"
    required_variant_ids: list[str]
    clip_count: int = Field(ge=0)
    exposure_ms: int = Field(ge=0)
    annotation_set_count: int = Field(ge=0)
    annotation_agreements: list[FallEventAnnotationAgreement]
    ground_truth_event_count: int = Field(ge=0)
    negative_clip_count: int = Field(ge=0)
    annotations_complete: bool
    agreement_gate_passed: bool
    adjudication_complete: bool
    minimum_data_gate_passed: bool
    provenance_gate_passed: bool
    capture_camera_gate_passed: bool
    variants: list[FallEventVariantEvaluation]
    event_metrics_ready_for_review: bool = False
    decision: str
    quality_status: QualityStatus
    raw_paths_persisted: Literal[False] = False
    annotator_refs_persisted: Literal[False] = False
    annotation_windows_persisted: Literal[False] = False
    candidate_windows_persisted: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    issues: list[QualityIssue] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_readiness(self) -> "FallEventEvaluationReadinessReport":
        variant_ids = [variant.variant_id for variant in self.variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("event evaluation variants must be unique")
        if sorted(variant_ids) != sorted(self.required_variant_ids):
            raise ValueError("event evaluation variants differ from required variants")
        if any(variant.clip_count != self.clip_count for variant in self.variants):
            raise ValueError("event evaluation variant clip count disagrees")
        if any(variant.exposure_ms != self.exposure_ms for variant in self.variants):
            raise ValueError("event evaluation variant exposure disagrees")
        if any(
            variant.ground_truth_event_count != self.ground_truth_event_count
            for variant in self.variants
        ):
            raise ValueError("event evaluation ground-truth count disagrees")
        if self.event_metrics_ready_for_review:
            gates = (
                self.annotations_complete,
                self.agreement_gate_passed,
                self.adjudication_complete,
                self.minimum_data_gate_passed,
                self.provenance_gate_passed,
                self.capture_camera_gate_passed,
            )
            if not all(gates):
                raise ValueError("event metrics cannot be ready while a gate is closed")
            if (
                self.fixture
                or self.synthetic
                or self.template_only
                or self.source_type is SourceType.FIXTURE
                or EVIDENCE_RANK[self.evidence_level]
                < EVIDENCE_RANK[EvidenceLevel.E2]
            ):
                raise ValueError("fixture or sub-E2 evidence cannot open event readiness")
        return self


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
