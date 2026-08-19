from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
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
    NETWORK_STREAM = "network_stream"
    SDK_EXPORT = "sdk_export"
    API_RESPONSE = "api_response"
    FIXTURE = "fixture"
    RUNTIME_SNAPSHOT = "runtime_snapshot"


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
    SourceType.NETWORK_STREAM: EvidenceLevel.E2,
    SourceType.SDK_EXPORT: EvidenceLevel.E2,
    SourceType.API_RESPONSE: EvidenceLevel.E3,
    SourceType.RUNTIME_SNAPSHOT: EvidenceLevel.E1,
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
    input_layout: Literal[
        "separate_files_synthetic_common_zero",
        "same_container_pts",
    ] = "separate_files_synthetic_common_zero"
    same_container_av: bool = False
    audio_start_offset_ms: float = Field(default=0.0, allow_inf_nan=False)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input_layout(self) -> "MultimodalPipelineReport":
        same_container = self.input_layout == "same_container_pts"
        if same_container != self.same_container_av:
            raise ValueError("input_layout and same_container_av disagree")
        if same_container and self.video_asset_id != self.audio_asset_id:
            raise ValueError("same-container report must reference one source asset")
        if not same_container and self.audio_start_offset_ms != 0.0:
            raise ValueError("separate-file replay must use synthetic common zero")
        return self


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


class PredictionFrameValue(ContractModel):
    """Per-frame prediction indicators adapted from the synced fall-detection core.

    Values are raw engineering measurements.  Candidate 0-3 scores produced by
    the synced algorithms are owner-only candidates, not formal assessments.
    """

    schema_version: str = "1.0"
    feature_version: str
    frame_sequence: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    person_detected: bool
    person_count: int = Field(ge=0)
    selected_track_id: int | None = None
    raw_posture: str | None = None
    posture: str | None = None
    bbox_aspect_ratio: float | None = None
    torso_tilt_deg: float | None = None
    knee_angle_deg: float | None = None
    center_speed_px_s: float | None = None
    horizontal_speed_frame_widths_s: float | None = None
    vertical_speed_frame_heights_s: float | None = None
    lying_duration_s: float | None = Field(default=None, ge=0.0)
    gait: dict[str, Any] = Field(default_factory=dict)
    sit_to_stand_state: str | None = None
    last_sit_to_stand: dict[str, Any] | None = None
    candidate_scores: dict[str, Any] = Field(default_factory=dict)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


class PredictionClipSummary(ContractModel):
    """Clip-level aggregate of the synced prediction indicators."""

    schema_version: str = "1.0"
    feature_version: str
    frames_processed: int = Field(ge=0)
    frames_with_primary_person: int = Field(ge=0)
    posture_frame_counts: dict[str, int] = Field(default_factory=dict)
    step_event_count: int = Field(ge=0)
    final_gait: dict[str, Any] = Field(default_factory=dict)
    sit_to_stand_completed_count: int = Field(ge=0)
    sit_to_stand_durations_s: list[float] = Field(default_factory=list)
    assessability: Literal["assessable", "not_assessable"]
    gate_failures: list[str] = Field(default_factory=list)
    meters_per_pixel: float = Field(ge=0.0)
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


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
    prediction_summary: PredictionClipSummary | None = None
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


class FallEventBundleAssemblyReport(ContractModel):
    """Path-free receipt for one atomically assembled evaluator bundle."""

    schema_version: Literal["1.0"] = "1.0"
    assembler_version: str = Field(min_length=1)
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture: bool
    evidence_level: EvidenceLevel
    source_type: SourceType
    capture_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_generator_policy_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    annotation_set_count: int = Field(ge=2)
    variant_ids: list[str] = Field(min_length=1)
    copied_source_file_count: int = Field(ge=1)
    preflight_decision: Literal[
        "event_metrics_ready_for_review",
        "tooling_only",
        "capture_gate_closed",
        "not_ready",
    ]
    preflight_quality_status: QualityStatus
    provenance_gate_passed: bool
    event_metrics_ready_for_review: bool
    source_paths_persisted: Literal[False] = False
    raw_media_copied: Literal[False] = False
    copied_sensitive_file_mode: Literal["0600"] = "0600"
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assembly_report(self) -> "FallEventBundleAssemblyReport":
        if len(self.variant_ids) != len(set(self.variant_ids)):
            raise ValueError("event bundle assembly variants must be unique")
        if self.fixture and self.evidence_level is not EvidenceLevel.E1:
            raise ValueError("fixture event bundle assembly must remain E1")
        if self.fixture != (self.source_type is SourceType.FIXTURE):
            raise ValueError("event bundle fixture marker disagrees with source type")
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


class SpeechSegment(ContractModel):
    """Formal D1 speech segment contract (design doc section 3).

    Transcript text stays owner-only; public evidence may only carry
    category, timing, counts, quality and status.
    """

    schema_version: str = "1.0"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    language: str
    confidence: float | None = None
    transcript_ref: str | None = None
    finalized: bool = True

    @model_validator(mode="after")
    def validate_bounds(self) -> "SpeechSegment":
        if self.end_ms < self.start_ms:
            raise ValueError("speech segment end precedes start")
        return self


class VoiceCandidate(ContractModel):
    """Help-request / fall-related voice candidate for human review.

    A voice candidate never confirms a fall and never emits a risk
    assessment by itself.
    """

    schema_version: str = "1.0"
    candidate_id: str = Field(min_length=3)
    category: Literal["help_request", "fall_related"]
    time_range: TimeRange = Field(default_factory=TimeRange)
    segment_ref: str | None = None
    matcher_revision: str = Field(min_length=1)
    review_status: Literal["pending_review", "confirmed", "rejected"] = (
        "pending_review"
    )
    risk_assessment_emitted: Literal[False] = False


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


class StreamCaptureTrack(ContractModel):
    stream_type: Literal["video", "audio"]
    source_stream_index: int = Field(ge=0)
    codec_name: str | None = None
    copied_packet_count: int = Field(ge=0)
    missing_timestamp_count: int = Field(ge=0)
    output_codec_name: str | None = None


class StreamCaptureReport(ContractModel):
    """Privacy-safe receipt for one bounded network/file stream remux."""

    schema_version: str = "1.0"
    capture_version: str
    evidence_level: EvidenceLevel
    source_type: SourceType
    endpoint_scheme: Literal["rtsp", "rtsps", "http", "https", "file", "local"]
    endpoint_supplied_via_environment: Literal[True] = True
    endpoint_value_persisted: Literal[False] = False
    endpoint_digest_persisted: Literal[False] = False
    endpoint_log_messages_persisted: Literal[False] = False
    transport: Literal["auto", "tcp", "udp"]
    requested_duration_ms: int = Field(gt=0)
    minimum_duration_ms: int = Field(gt=0)
    captured_media_span_ms: int = Field(ge=0)
    open_timeout_ms: int = Field(gt=0)
    read_timeout_ms: int = Field(gt=0)
    packet_limit: int = Field(gt=0)
    inspected_packet_count: int = Field(ge=0)
    copied_packet_count: int = Field(ge=0)
    termination_reason: Literal[
        "duration_limit",
        "end_of_stream",
        "packet_limit",
        "wall_time_limit",
    ]
    audio_required: bool
    first_video_packet_keyframe: bool
    tracks: list[StreamCaptureTrack] = Field(default_factory=list)
    output_artifact: str
    raw_media_persisted: Literal[True] = True
    received_time_is_device_time: Literal[False] = False
    media_probe: MediaProbeReport
    capture_artifact_ready: bool
    same_container_multimodal_ready: bool
    device_platform_integration_proven: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


class StreamQualificationTrackSignature(ContractModel):
    """Path-free media layout used to compare independent stream opens."""

    stream_type: Literal["video", "audio"]
    codec_name: str | None = None
    time_base: str | None = None
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    pixel_format: str | None = None
    average_rate: str | None = None
    sample_rate_hz: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    channel_layout: str | None = None

    @model_validator(mode="after")
    def validate_type_specific_fields(self):
        video_fields = (
            self.width_px,
            self.height_px,
            self.pixel_format,
            self.average_rate,
        )
        audio_fields = (
            self.sample_rate_hz,
            self.channels,
            self.channel_layout,
        )
        if self.stream_type == "video" and any(
            value is not None for value in audio_fields
        ):
            raise ValueError("video signature cannot include audio fields")
        if self.stream_type == "audio" and any(
            value is not None for value in video_fields
        ):
            raise ValueError("audio signature cannot include video fields")
        return self


class StreamQualificationAttempt(ContractModel):
    attempt_index: int = Field(ge=1)
    status: Literal["captured_ready", "captured_not_ready", "failed"]
    elapsed_ms: int = Field(ge=0)
    failure_code: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*$",
        max_length=64,
    )
    output_artifact: str | None = None
    capture_report_artifact: str | None = None
    captured_media_span_ms: int | None = Field(default=None, ge=0)
    termination_reason: Literal[
        "duration_limit",
        "end_of_stream",
        "packet_limit",
        "wall_time_limit",
    ] | None = None
    capture_artifact_ready: bool = False
    same_container_multimodal_ready: bool = False
    track_signature: list[StreamQualificationTrackSignature] = Field(
        default_factory=list
    )
    audio_minus_video_start_ms: float | None = None

    @model_validator(mode="after")
    def validate_attempt_state(self):
        artifact_fields = (
            self.output_artifact,
            self.capture_report_artifact,
            self.captured_media_span_ms,
            self.termination_reason,
        )
        if self.status == "failed":
            if not self.failure_code:
                raise ValueError("failed stream attempt requires failure_code")
            if any(value is not None for value in artifact_fields):
                raise ValueError("failed stream attempt cannot reference artifacts")
            if (
                self.capture_artifact_ready
                or self.same_container_multimodal_ready
                or self.track_signature
                or self.audio_minus_video_start_ms is not None
            ):
                raise ValueError("failed stream attempt cannot publish capture facts")
            return self

        if self.failure_code is not None:
            raise ValueError("captured stream attempt cannot include failure_code")
        if any(value is None for value in artifact_fields):
            raise ValueError("captured stream attempt requires artifact facts")
        output_path = PurePosixPath(self.output_artifact)
        report_path = PurePosixPath(self.capture_report_artifact)
        if (
            output_path.is_absolute()
            or len(output_path.parts) != 2
            or output_path.parts[0] != "artifacts"
            or output_path.suffix != ".mkv"
            or any(part in {"", ".", ".."} for part in output_path.parts)
            or "\\" in self.output_artifact
        ):
            raise ValueError("stream output artifact must be artifacts/*.mkv")
        if (
            report_path.is_absolute()
            or len(report_path.parts) != 2
            or report_path.parts[0] != "reports"
            or report_path.suffix != ".json"
            or any(part in {"", ".", ".."} for part in report_path.parts)
            or "\\" in self.capture_report_artifact
        ):
            raise ValueError("stream capture report must be reports/*.json")
        if self.capture_artifact_ready and not self.track_signature:
            raise ValueError("ready capture artifact requires track signature")
        return self


class StreamQualificationReport(ContractModel):
    """Aggregate receipt for multiple independent bounded stream opens."""

    schema_version: str = "1.0"
    qualification_version: str
    evidence_level: EvidenceLevel
    source_type: SourceType
    endpoint_scheme: Literal["rtsp", "rtsps", "http", "https", "file", "local"]
    endpoint_supplied_via_environment: Literal[True] = True
    endpoint_value_persisted: Literal[False] = False
    endpoint_digest_persisted: Literal[False] = False
    endpoint_variable_persisted: Literal[False] = False
    endpoint_log_messages_persisted: Literal[False] = False
    transport: Literal["auto", "tcp", "udp"]
    attempt_count: int = Field(ge=2, le=20)
    requested_duration_ms_per_attempt: int = Field(gt=0)
    minimum_duration_ms_per_attempt: int = Field(gt=0)
    audio_required: bool
    attempts: list[StreamQualificationAttempt] = Field(default_factory=list)
    captured_attempt_count: int = Field(ge=0)
    ready_attempt_count: int = Field(ge=0)
    not_ready_attempt_count: int = Field(ge=0)
    failed_attempt_count: int = Field(ge=0)
    unique_track_signature_count: int = Field(ge=0)
    track_signatures_consistent: bool
    scheduled_reopen_sequence_proven: bool
    repeated_capture_gate_ready: bool
    m2c_capture_bundle_ready: Literal[False] = False
    involuntary_disconnect_recovery_proven: Literal[False] = False
    long_running_stability_proven: Literal[False] = False
    network_impairment_tolerance_proven: Literal[False] = False
    device_platform_integration_proven: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_qualification_counts_and_gate(self):
        if len(self.attempts) != self.attempt_count:
            raise ValueError("attempt list must match attempt_count")
        if [item.attempt_index for item in self.attempts] != list(
            range(1, self.attempt_count + 1)
        ):
            raise ValueError("stream attempt indexes must be contiguous")
        captured = sum(item.status != "failed" for item in self.attempts)
        ready = sum(item.status == "captured_ready" for item in self.attempts)
        not_ready = sum(
            item.status == "captured_not_ready" for item in self.attempts
        )
        failed = sum(item.status == "failed" for item in self.attempts)
        signature_keys = {
            tuple(
                tuple(sorted(track.model_dump(mode="json").items()))
                for track in item.track_signature
            )
            for item in self.attempts
            if item.track_signature
        }
        if self.unique_track_signature_count != len(signature_keys):
            raise ValueError("unique track signature count is inconsistent")
        signature_attempt_count = sum(
            bool(item.track_signature) for item in self.attempts
        )
        expected_consistency = bool(
            captured > 0
            and signature_attempt_count == captured
            and len(signature_keys) == 1
        )
        if self.track_signatures_consistent is not expected_consistency:
            raise ValueError("track signature consistency is inconsistent")
        for item in self.attempts:
            if item.status == "failed":
                continue
            requested_ready = (
                item.same_container_multimodal_ready
                if self.audio_required
                else item.capture_artifact_ready
            )
            if (item.status == "captured_ready") is not requested_ready:
                raise ValueError("attempt status must match requested readiness")
        if (
            self.captured_attempt_count != captured
            or self.ready_attempt_count != ready
            or self.not_ready_attempt_count != not_ready
            or self.failed_attempt_count != failed
            or captured != ready + not_ready
        ):
            raise ValueError("stream qualification attempt counts are inconsistent")
        if self.scheduled_reopen_sequence_proven is not (ready >= 2):
            raise ValueError("scheduled reopen proof must require two ready attempts")
        expected_gate = bool(
            ready == self.attempt_count
            and failed == 0
            and not_ready == 0
            and self.track_signatures_consistent
            and self.unique_track_signature_count == 1
        )
        if self.repeated_capture_gate_ready is not expected_gate:
            raise ValueError("repeated capture gate is inconsistent")
        return self


StreamSessionFailureCode = Literal[
    "open_failed",
    "remux_failed",
    "video_track_layout_invalid",
    "audio_track_layout_invalid",
    "required_audio_track_missing",
    "packet_timestamp_missing",
    "video_keyframe_missing",
    "video_packets_missing",
    "audio_packets_missing",
    "media_artifact_missing",
    "output_verification_failed",
    "stream_capture_failed",
]


class StreamSessionSegment(ContractModel):
    """One independently opened and independently persisted session segment."""

    segment_index: int = Field(ge=1)
    status: Literal["captured_ready", "captured_not_ready", "failed"]
    started_offset_ms: int = Field(ge=0)
    finished_offset_ms: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    gap_before_ms: int = Field(ge=0)
    failure_code: StreamSessionFailureCode | None = None
    output_artifact: str | None = None
    capture_report_artifact: str | None = None
    captured_media_span_ms: int | None = Field(default=None, ge=0)
    termination_reason: Literal[
        "duration_limit",
        "end_of_stream",
        "packet_limit",
        "wall_time_limit",
    ] | None = None
    capture_artifact_ready: bool = False
    same_container_multimodal_ready: bool = False
    track_signature: list[StreamQualificationTrackSignature] = Field(
        default_factory=list
    )
    audio_minus_video_start_ms: float | None = None

    @model_validator(mode="after")
    def validate_segment_state(self):
        if self.finished_offset_ms < self.started_offset_ms:
            raise ValueError("session segment finishes before it starts")
        if self.elapsed_ms != self.finished_offset_ms - self.started_offset_ms:
            raise ValueError("session segment elapsed time is inconsistent")
        artifact_fields = (
            self.output_artifact,
            self.capture_report_artifact,
            self.captured_media_span_ms,
            self.termination_reason,
        )
        if self.status == "failed":
            if not self.failure_code:
                raise ValueError("failed session segment requires failure_code")
            if any(value is not None for value in artifact_fields):
                raise ValueError("failed session segment cannot reference artifacts")
            if (
                self.capture_artifact_ready
                or self.same_container_multimodal_ready
                or self.track_signature
                or self.audio_minus_video_start_ms is not None
            ):
                raise ValueError("failed session segment cannot publish capture facts")
            return self

        if self.failure_code is not None:
            raise ValueError("captured session segment cannot include failure_code")
        if any(value is None for value in artifact_fields):
            raise ValueError("captured session segment requires artifact facts")
        output_path = PurePosixPath(self.output_artifact)
        report_path = PurePosixPath(self.capture_report_artifact)
        if (
            output_path.is_absolute()
            or len(output_path.parts) != 2
            or output_path.parts[0] != "artifacts"
            or output_path.suffix != ".mkv"
            or any(part in {"", ".", ".."} for part in output_path.parts)
            or "\\" in self.output_artifact
        ):
            raise ValueError("session output artifact must be artifacts/*.mkv")
        if (
            report_path.is_absolute()
            or len(report_path.parts) != 2
            or report_path.parts[0] != "reports"
            or report_path.suffix != ".json"
            or any(part in {"", ".", ".."} for part in report_path.parts)
            or "\\" in self.capture_report_artifact
        ):
            raise ValueError("session capture report must be reports/*.json")
        if self.capture_artifact_ready and not self.track_signature:
            raise ValueError("ready session artifact requires track signature")
        return self


class StreamSessionRecoveryEvent(ContractModel):
    """A contiguous unready streak followed by a new ready artifact."""

    interruption_start_segment_index: int = Field(ge=1)
    interruption_end_segment_index: int = Field(ge=1)
    recovered_segment_index: int = Field(ge=2)
    interrupted_segment_count: int = Field(ge=1)
    reopen_delay_ms: int = Field(ge=0)
    interruption_to_ready_artifact_ms: int = Field(ge=0)


class StreamSessionReport(ContractModel):
    """Auditable ledger for a sequence of independent bounded stream opens."""

    schema_version: str = "1.0"
    session_version: str
    evidence_level: EvidenceLevel
    source_type: SourceType
    endpoint_scheme: Literal["rtsp", "rtsps", "http", "https", "file", "local"]
    endpoint_supplied_via_environment: bool = False
    endpoint_value_persisted: Literal[False] = False
    endpoint_digest_persisted: Literal[False] = False
    endpoint_variable_persisted: Literal[False] = False
    endpoint_log_messages_persisted: Literal[False] = False
    transport: Literal["auto", "tcp", "udp"]
    segment_count: int = Field(ge=2, le=1000)
    requested_duration_ms_per_segment: int = Field(gt=0)
    minimum_duration_ms_per_segment: int = Field(gt=0)
    open_timeout_ms: int = Field(gt=0)
    read_timeout_ms: int = Field(gt=0)
    audio_required: bool
    failure_backoff_ms: int = Field(ge=0)
    minimum_session_wall_ms: int = Field(ge=0)
    minimum_ready_media_ms: int = Field(ge=0)
    long_run_threshold_ms: Literal[1800000] = 1_800_000
    session_elapsed_ms: int = Field(ge=0)
    ready_media_span_ms: int = Field(ge=0)
    segments: list[StreamSessionSegment] = Field(default_factory=list)
    recovery_events: list[StreamSessionRecoveryEvent] = Field(default_factory=list)
    captured_segment_count: int = Field(ge=0)
    ready_segment_count: int = Field(ge=0)
    not_ready_segment_count: int = Field(ge=0)
    failed_segment_count: int = Field(ge=0)
    longest_interruption_streak: int = Field(ge=0)
    unique_track_signature_count: int = Field(ge=0)
    track_signatures_consistent: bool
    independent_segment_artifacts_proven: bool
    supervisor_reopen_attempted: bool
    supervisor_reopen_recovery_observed: bool
    all_segment_capture_gate_ready: bool
    session_duration_gate_ready: bool
    session_media_duration_gate_ready: bool
    session_gate_ready: bool
    segmented_session_long_running_stability_proven: bool
    same_raw_reconnect_attempted: Literal[False] = False
    cross_segment_media_concatenated: Literal[False] = False
    involuntary_disconnect_recovery_proven: Literal[False] = False
    single_connection_long_running_stability_proven: Literal[False] = False
    network_impairment_tolerance_proven: Literal[False] = False
    device_platform_integration_proven: Literal[False] = False
    m2c_capture_bundle_ready: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_session_ledger(self):
        if len(self.segments) != self.segment_count:
            raise ValueError("session segment list must match segment_count")
        if [item.segment_index for item in self.segments] != list(
            range(1, self.segment_count + 1)
        ):
            raise ValueError("session segment indexes must be contiguous")
        if self.minimum_duration_ms_per_segment > self.requested_duration_ms_per_segment:
            raise ValueError("session minimum duration exceeds request")
        previous_finished = 0
        for item in self.segments:
            expected_gap = item.started_offset_ms - previous_finished
            if expected_gap < 0 or item.gap_before_ms != expected_gap:
                raise ValueError("session segment gap ledger is inconsistent")
            if item.status != "failed" and (
                item.output_artifact
                != f"artifacts/stream-session-{item.segment_index:03d}.mkv"
                or item.capture_report_artifact
                != f"reports/stream-session-{item.segment_index:03d}.json"
            ):
                raise ValueError("session segment artifact names are inconsistent")
            if item.status != "failed":
                requested_ready = (
                    item.same_container_multimodal_ready
                    if self.audio_required
                    else item.capture_artifact_ready
                )
                if (item.status == "captured_ready") is not requested_ready:
                    raise ValueError("session segment status must match requested readiness")
            previous_finished = item.finished_offset_ms
        if self.session_elapsed_ms != self.segments[-1].finished_offset_ms:
            raise ValueError("session elapsed time must close at the final segment")
        ready_media_span_ms = sum(
            item.captured_media_span_ms or 0
            for item in self.segments
            if item.status == "captured_ready"
        )
        if self.ready_media_span_ms != ready_media_span_ms:
            raise ValueError("session ready media span is inconsistent")

        captured = sum(item.status != "failed" for item in self.segments)
        ready = sum(item.status == "captured_ready" for item in self.segments)
        not_ready = sum(
            item.status == "captured_not_ready" for item in self.segments
        )
        failed = sum(item.status == "failed" for item in self.segments)
        if (
            self.captured_segment_count != captured
            or self.ready_segment_count != ready
            or self.not_ready_segment_count != not_ready
            or self.failed_segment_count != failed
            or captured != ready + not_ready
        ):
            raise ValueError("session segment counts are inconsistent")

        signature_keys = {
            tuple(
                tuple(sorted(track.model_dump(mode="json").items()))
                for track in item.track_signature
            )
            for item in self.segments
            if item.track_signature
        }
        if self.unique_track_signature_count != len(signature_keys):
            raise ValueError("session unique track signature count is inconsistent")
        expected_consistency = bool(
            captured > 0
            and sum(bool(item.track_signature) for item in self.segments)
            == captured
            and len(signature_keys) == 1
        )
        if self.track_signatures_consistent is not expected_consistency:
            raise ValueError("session track signature consistency is inconsistent")

        captured_paths = [
            item.output_artifact for item in self.segments if item.output_artifact
        ]
        independent = bool(
            captured > 0 and len(captured_paths) == len(set(captured_paths))
        )
        if self.independent_segment_artifacts_proven is not independent:
            raise ValueError("independent session artifact result is inconsistent")

        expected_events: list[dict[str, int]] = []
        streak_start: int | None = None
        streak_end: int | None = None
        longest_streak = 0
        for item in self.segments:
            if item.status != "captured_ready":
                if streak_start is None:
                    streak_start = item.segment_index
                streak_end = item.segment_index
                longest_streak = max(
                    longest_streak,
                    streak_end - streak_start + 1,
                )
                continue
            if streak_start is None or streak_end is None:
                continue
            first_interrupted = self.segments[streak_start - 1]
            last_interrupted = self.segments[streak_end - 1]
            expected_events.append(
                {
                    "interruption_start_segment_index": streak_start,
                    "interruption_end_segment_index": streak_end,
                    "recovered_segment_index": item.segment_index,
                    "interrupted_segment_count": streak_end - streak_start + 1,
                    "reopen_delay_ms": (
                        item.started_offset_ms - last_interrupted.finished_offset_ms
                    ),
                    "interruption_to_ready_artifact_ms": (
                        item.finished_offset_ms - first_interrupted.finished_offset_ms
                    ),
                }
            )
            streak_start = None
            streak_end = None
        if self.longest_interruption_streak != longest_streak:
            raise ValueError("session interruption streak is inconsistent")
        actual_events = [
            item.model_dump(mode="json") for item in self.recovery_events
        ]
        if actual_events != expected_events:
            raise ValueError("session recovery event ledger is inconsistent")
        reopen_attempted = any(
            item.status != "captured_ready" and item.segment_index < self.segment_count
            for item in self.segments
        )
        recovery_observed = bool(expected_events)
        if self.supervisor_reopen_attempted is not reopen_attempted:
            raise ValueError("supervisor reopen attempt result is inconsistent")
        if self.supervisor_reopen_recovery_observed is not recovery_observed:
            raise ValueError("supervisor recovery observation is inconsistent")

        all_capture_ready = bool(
            ready == self.segment_count
            and not_ready == 0
            and failed == 0
            and independent
            and expected_consistency
            and len(signature_keys) == 1
        )
        duration_ready = self.session_elapsed_ms >= self.minimum_session_wall_ms
        media_duration_ready = (
            self.ready_media_span_ms >= self.minimum_ready_media_ms
        )
        session_ready = (
            all_capture_ready and duration_ready and media_duration_ready
        )
        long_running = bool(
            session_ready
            and self.minimum_session_wall_ms >= self.long_run_threshold_ms
            and self.session_elapsed_ms >= self.long_run_threshold_ms
            and self.minimum_ready_media_ms >= self.long_run_threshold_ms
            and self.ready_media_span_ms >= self.long_run_threshold_ms
        )
        if self.all_segment_capture_gate_ready is not all_capture_ready:
            raise ValueError("all-segment capture gate is inconsistent")
        if self.session_duration_gate_ready is not duration_ready:
            raise ValueError("session duration gate is inconsistent")
        if self.session_media_duration_gate_ready is not media_duration_ready:
            raise ValueError("session media duration gate is inconsistent")
        if self.session_gate_ready is not session_ready:
            raise ValueError("session gate is inconsistent")
        if self.segmented_session_long_running_stability_proven is not long_running:
            raise ValueError("segmented long-running stability result is inconsistent")
        return self


StreamRecoveryBehavior = Literal["full", "reject"]


class StreamRecoveryInjectionResult(ContractModel):
    segment_index: int = Field(ge=1)
    behavior: StreamRecoveryBehavior
    request_count: int = Field(ge=0)
    body_bytes_sent: int = Field(ge=0)
    body_chunk_count: int = Field(ge=0)
    rejection_event_count: int = Field(ge=0)
    scenario_exercised: bool

    @model_validator(mode="after")
    def validate_recovery_injection(self):
        if (self.body_bytes_sent > 0) is not (self.body_chunk_count > 0):
            raise ValueError("recovery injection body telemetry is inconsistent")
        exercised = bool(
            self.request_count > 0
            and (
                (
                    self.behavior == "full"
                    and self.body_bytes_sent > 0
                    and self.rejection_event_count == 0
                )
                or (
                    self.behavior == "reject"
                    and self.body_bytes_sent == 0
                    and self.rejection_event_count > 0
                )
            )
        )
        if self.scenario_exercised is not exercised:
            raise ValueError("recovery injection execution telemetry is inconsistent")
        return self


class StreamRecoveryExerciseReport(ContractModel):
    """Fixture-only proof that the external supervisor reopens after rejection."""

    schema_version: str = "1.0"
    exercise_version: str
    evidence_level: Literal[EvidenceLevel.E1] = EvidenceLevel.E1
    source_type: Literal[SourceType.FIXTURE] = SourceType.FIXTURE
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_byte_size: int = Field(gt=0)
    fixture_path_persisted: Literal[False] = False
    endpoint_scheme: Literal["http"] = "http"
    endpoint_loopback_only: Literal[True] = True
    endpoint_value_persisted: Literal[False] = False
    endpoint_port_persisted: Literal[False] = False
    endpoint_log_messages_persisted: Literal[False] = False
    profile: Literal["ready_http_503_ready"] = "ready_http_503_ready"
    injections: list[StreamRecoveryInjectionResult] = Field(default_factory=list)
    all_injections_exercised: bool
    session: StreamSessionReport
    controlled_supervisor_recovery_gate_ready: bool
    packet_loss_injected: Literal[False] = False
    rtsp_transport_tested: Literal[False] = False
    same_connection_reconnect_proven: Literal[False] = False
    involuntary_disconnect_recovery_proven: Literal[False] = False
    network_impairment_tolerance_proven: Literal[False] = False
    long_running_stability_proven: Literal[False] = False
    device_platform_integration_proven: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_recovery_exercise(self):
        expected_behaviors = ("full", "reject", "full")
        if len(self.injections) != 3:
            raise ValueError("recovery exercise requires three injections")
        if [item.segment_index for item in self.injections] != [1, 2, 3]:
            raise ValueError("recovery injection indexes must be contiguous")
        if tuple(item.behavior for item in self.injections) != expected_behaviors:
            raise ValueError("recovery exercise behavior order is inconsistent")
        all_exercised = all(item.scenario_exercised for item in self.injections)
        if self.all_injections_exercised is not all_exercised:
            raise ValueError("recovery injection aggregate is inconsistent")
        session = self.session
        expected_session = bool(
            session.evidence_level == EvidenceLevel.E1
            and session.source_type == SourceType.FIXTURE
            and session.endpoint_scheme == "http"
            and not session.endpoint_supplied_via_environment
            and session.transport == "auto"
            and session.segment_count == 3
            and [item.status for item in session.segments]
            == ["captured_ready", "failed", "captured_ready"]
            and session.segments[1].failure_code == "open_failed"
            and session.ready_segment_count == 2
            and session.failed_segment_count == 1
            and session.not_ready_segment_count == 0
            and session.unique_track_signature_count == 1
            and session.track_signatures_consistent
            and session.independent_segment_artifacts_proven
            and session.supervisor_reopen_attempted
            and session.supervisor_reopen_recovery_observed
            and len(session.recovery_events) == 1
            and session.recovery_events[0].interruption_start_segment_index == 2
            and session.recovery_events[0].interruption_end_segment_index == 2
            and session.recovery_events[0].recovered_segment_index == 3
            and not session.all_segment_capture_gate_ready
            and not session.session_gate_ready
        )
        gate = all_exercised and expected_session
        if self.controlled_supervisor_recovery_gate_ready is not gate:
            raise ValueError("controlled supervisor recovery gate is inconsistent")
        return self


StreamFaultScenarioName = Literal[
    "healthy_control",
    "chunk_delay_jitter",
    "http_rejection",
    "initial_response_stall",
    "midstream_stall",
    "truncated_transfer",
    "connection_reset",
]
StreamFaultExpectedStatus = Literal[
    "captured_ready",
    "failed",
    "not_ready_or_failed",
]
StreamFaultFailureCode = Literal[
    "open_failed",
    "remux_failed",
    "video_track_layout_invalid",
    "audio_track_layout_invalid",
    "required_audio_track_missing",
    "packet_timestamp_missing",
    "video_keyframe_missing",
    "video_packets_missing",
    "audio_packets_missing",
    "media_artifact_missing",
    "output_verification_failed",
    "stream_capture_failed",
]
STREAM_FAULT_SCENARIO_ORDER: tuple[str, ...] = (
    "healthy_control",
    "chunk_delay_jitter",
    "http_rejection",
    "initial_response_stall",
    "midstream_stall",
    "truncated_transfer",
    "connection_reset",
)
STREAM_FAULT_EXPECTED_STATUS: dict[str, str] = {
    "healthy_control": "captured_ready",
    "chunk_delay_jitter": "captured_ready",
    "http_rejection": "failed",
    "initial_response_stall": "failed",
    "midstream_stall": "not_ready_or_failed",
    "truncated_transfer": "not_ready_or_failed",
    "connection_reset": "not_ready_or_failed",
}


class StreamFaultCaseResult(ContractModel):
    """Privacy-safe outcome of one controlled loopback HTTP behavior."""

    case_index: int = Field(ge=1)
    scenario: StreamFaultScenarioName
    fault_injected: bool
    expected_status: StreamFaultExpectedStatus
    actual_status: Literal[
        "captured_ready",
        "captured_not_ready",
        "failed",
    ]
    elapsed_ms: int = Field(ge=0)
    elapsed_limit_ms: int = Field(gt=0)
    bounded_completion: bool
    expectation_met: bool
    body_byte_limit: int | None = Field(default=None, ge=0)
    stall_duration_ms: int | None = Field(default=None, gt=0)
    chunk_size_bytes: int | None = Field(default=None, gt=0)
    chunk_delay_min_ms: int | None = Field(default=None, ge=0)
    chunk_delay_max_ms: int | None = Field(default=None, ge=0)
    request_count: int = Field(ge=0)
    body_bytes_sent: int = Field(ge=0)
    body_chunk_count: int = Field(ge=0)
    delay_event_count: int = Field(ge=0)
    stall_event_count: int = Field(ge=0)
    rejection_event_count: int = Field(ge=0)
    reset_event_count: int = Field(ge=0)
    early_close_event_count: int = Field(ge=0)
    scenario_exercised: bool
    failure_code: StreamFaultFailureCode | None = None
    output_artifact: str | None = None
    capture_report_artifact: str | None = None
    captured_media_span_ms: int | None = Field(default=None, ge=0)
    termination_reason: Literal[
        "duration_limit",
        "end_of_stream",
        "packet_limit",
        "wall_time_limit",
    ] | None = None
    capture_artifact_ready: bool = False
    same_container_multimodal_ready: bool = False

    @model_validator(mode="after")
    def validate_fault_case(self):
        expected_status = STREAM_FAULT_EXPECTED_STATUS[self.scenario]
        if self.expected_status != expected_status:
            raise ValueError("fault case expected status is inconsistent")
        if self.fault_injected is not (self.scenario != "healthy_control"):
            raise ValueError("fault injection flag is inconsistent")
        if (self.body_bytes_sent > 0) is not (self.body_chunk_count > 0):
            raise ValueError("fault case body telemetry is inconsistent")
        scenario_parameters_valid = bool(
            (
                self.scenario == "healthy_control"
                and self.body_byte_limit is None
                and self.stall_duration_ms is None
                and self.chunk_size_bytes is None
                and self.chunk_delay_min_ms is None
                and self.chunk_delay_max_ms is None
            )
            or (
                self.scenario == "chunk_delay_jitter"
                and self.body_byte_limit is None
                and self.stall_duration_ms is None
                and self.chunk_size_bytes is not None
                and self.chunk_delay_min_ms is not None
                and self.chunk_delay_max_ms is not None
                and self.chunk_delay_min_ms <= self.chunk_delay_max_ms
                and self.chunk_delay_max_ms > 0
            )
            or (
                self.scenario == "http_rejection"
                and self.body_byte_limit == 0
                and self.stall_duration_ms is None
                and self.chunk_size_bytes is None
                and self.chunk_delay_min_ms is None
                and self.chunk_delay_max_ms is None
            )
            or (
                self.scenario == "initial_response_stall"
                and self.body_byte_limit == 0
                and self.stall_duration_ms is not None
                and self.chunk_size_bytes is None
                and self.chunk_delay_min_ms is None
                and self.chunk_delay_max_ms is None
            )
            or (
                self.scenario == "midstream_stall"
                and self.body_byte_limit is not None
                and self.body_byte_limit > 0
                and self.stall_duration_ms is not None
                and self.chunk_size_bytes is None
                and self.chunk_delay_min_ms is None
                and self.chunk_delay_max_ms is None
            )
            or (
                self.scenario in {"truncated_transfer", "connection_reset"}
                and self.body_byte_limit is not None
                and self.body_byte_limit > 0
                and self.stall_duration_ms is None
                and self.chunk_size_bytes is None
                and self.chunk_delay_min_ms is None
                and self.chunk_delay_max_ms is None
            )
        )
        if not scenario_parameters_valid:
            raise ValueError("fault case injection parameters are inconsistent")
        irrelevant_events_zero = bool(
            (
                self.scenario == "healthy_control"
                and self.delay_event_count == 0
                and self.stall_event_count == 0
                and self.rejection_event_count == 0
                and self.reset_event_count == 0
                and self.early_close_event_count == 0
            )
            or (
                self.scenario == "chunk_delay_jitter"
                and self.stall_event_count == 0
                and self.rejection_event_count == 0
                and self.reset_event_count == 0
                and self.early_close_event_count == 0
            )
            or (
                self.scenario == "http_rejection"
                and self.delay_event_count == 0
                and self.stall_event_count == 0
                and self.reset_event_count == 0
                and self.early_close_event_count == 0
            )
            or (
                self.scenario
                in {"initial_response_stall", "midstream_stall"}
                and self.delay_event_count == 0
                and self.rejection_event_count == 0
                and self.reset_event_count == 0
                and self.early_close_event_count == 0
            )
            or (
                self.scenario == "truncated_transfer"
                and self.delay_event_count == 0
                and self.stall_event_count == 0
                and self.rejection_event_count == 0
                and self.reset_event_count == 0
            )
            or (
                self.scenario == "connection_reset"
                and self.delay_event_count == 0
                and self.stall_event_count == 0
                and self.rejection_event_count == 0
                and self.early_close_event_count == 0
            )
        )
        exercised = bool(
            self.request_count > 0
            and irrelevant_events_zero
            and (
                (self.scenario == "healthy_control" and self.body_bytes_sent > 0)
                or (
                    self.scenario == "chunk_delay_jitter"
                    and self.body_bytes_sent > 0
                    and self.delay_event_count > 0
                )
                or (
                    self.scenario == "http_rejection"
                    and self.rejection_event_count > 0
                    and self.body_bytes_sent == 0
                )
                or (
                    self.scenario == "initial_response_stall"
                    and self.stall_event_count > 0
                    and self.body_bytes_sent == 0
                )
                or (
                    self.scenario == "midstream_stall"
                    and self.stall_event_count > 0
                    and self.body_bytes_sent > 0
                )
                or (
                    self.scenario == "truncated_transfer"
                    and self.early_close_event_count > 0
                    and self.body_bytes_sent > 0
                )
                or (
                    self.scenario == "connection_reset"
                    and self.reset_event_count > 0
                    and self.body_bytes_sent > 0
                )
            )
        )
        if self.scenario_exercised is not exercised:
            raise ValueError("fault case execution telemetry is inconsistent")
        if self.bounded_completion is not (
            self.elapsed_ms <= self.elapsed_limit_ms
        ):
            raise ValueError("fault case bounded completion is inconsistent")
        expected_met = bool(
            (
                self.expected_status == "captured_ready"
                and self.actual_status == "captured_ready"
            )
            or (
                self.expected_status == "failed"
                and self.actual_status == "failed"
            )
            or (
                self.expected_status == "not_ready_or_failed"
                and self.actual_status != "captured_ready"
            )
        )
        if self.expectation_met is not expected_met:
            raise ValueError("fault case expectation result is inconsistent")

        artifact_facts = (
            self.output_artifact,
            self.capture_report_artifact,
            self.captured_media_span_ms,
            self.termination_reason,
        )
        if self.actual_status == "failed":
            if not self.failure_code:
                raise ValueError("failed fault case requires failure_code")
            if any(value is not None for value in artifact_facts):
                raise ValueError("failed fault case cannot reference artifacts")
            if self.capture_artifact_ready or self.same_container_multimodal_ready:
                raise ValueError("failed fault case cannot publish readiness")
            return self

        if self.failure_code is not None:
            raise ValueError("captured fault case cannot include failure_code")
        if any(value is None for value in artifact_facts):
            raise ValueError("captured fault case requires artifact facts")
        output_path = PurePosixPath(self.output_artifact)
        report_path = PurePosixPath(self.capture_report_artifact)
        if (
            output_path.is_absolute()
            or len(output_path.parts) != 2
            or output_path.parts[0] != "artifacts"
            or output_path.suffix != ".mkv"
            or any(part in {"", ".", ".."} for part in output_path.parts)
            or "\\" in self.output_artifact
        ):
            raise ValueError("fault output artifact must be artifacts/*.mkv")
        if (
            report_path.is_absolute()
            or len(report_path.parts) != 2
            or report_path.parts[0] != "reports"
            or report_path.suffix != ".json"
            or any(part in {"", ".", ".."} for part in report_path.parts)
            or "\\" in self.capture_report_artifact
        ):
            raise ValueError("fault capture report must be reports/*.json")
        expected_actual = (
            "captured_ready"
            if self.same_container_multimodal_ready
            else "captured_not_ready"
        )
        if self.actual_status != expected_actual:
            raise ValueError("fault case status must match requested readiness")
        return self


class StreamFaultMatrixReport(ContractModel):
    """Aggregate receipt for a fixed controlled HTTP fault matrix."""

    schema_version: str = "1.0"
    matrix_version: str
    evidence_level: Literal[EvidenceLevel.E1] = EvidenceLevel.E1
    source_type: Literal[SourceType.FIXTURE] = SourceType.FIXTURE
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_byte_size: int = Field(gt=0)
    fixture_path_persisted: Literal[False] = False
    endpoint_scheme: Literal["http"] = "http"
    endpoint_loopback_only: Literal[True] = True
    endpoint_value_persisted: Literal[False] = False
    endpoint_port_persisted: Literal[False] = False
    endpoint_log_messages_persisted: Literal[False] = False
    requested_duration_ms: int = Field(gt=0)
    minimum_duration_ms: int = Field(gt=0)
    open_timeout_ms: int = Field(gt=0)
    read_timeout_ms: int = Field(gt=0)
    elapsed_limit_ms: int = Field(gt=0)
    scenario_count: int = Field(ge=1)
    cases: list[StreamFaultCaseResult] = Field(default_factory=list)
    captured_case_count: int = Field(ge=0)
    ready_case_count: int = Field(ge=0)
    not_ready_case_count: int = Field(ge=0)
    failed_case_count: int = Field(ge=0)
    bounded_case_count: int = Field(ge=0)
    expectation_met_case_count: int = Field(ge=0)
    scenario_exercised_case_count: int = Field(ge=0)
    unexpected_ready_case_count: int = Field(ge=0)
    all_cases_bounded: bool
    all_expected_outcomes_met: bool
    all_scenarios_exercised: bool
    controlled_http_fault_matrix_executed: bool
    fault_detection_gate_ready: bool
    packet_loss_injected: Literal[False] = False
    rtsp_transport_tested: Literal[False] = False
    reconnect_attempted: Literal[False] = False
    involuntary_disconnect_recovery_proven: Literal[False] = False
    network_impairment_tolerance_proven: Literal[False] = False
    long_running_stability_proven: Literal[False] = False
    device_platform_integration_proven: Literal[False] = False
    m2c_capture_bundle_ready: Literal[False] = False
    risk_assessment_emitted: Literal[False] = False
    alert_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fault_matrix(self):
        if self.scenario_count != len(STREAM_FAULT_SCENARIO_ORDER):
            raise ValueError("fault matrix must contain the fixed scenario count")
        if len(self.cases) != self.scenario_count:
            raise ValueError("fault case list must match scenario_count")
        if [item.case_index for item in self.cases] != list(
            range(1, self.scenario_count + 1)
        ):
            raise ValueError("fault case indexes must be contiguous")
        if tuple(item.scenario for item in self.cases) != (
            STREAM_FAULT_SCENARIO_ORDER
        ):
            raise ValueError("fault cases must use the fixed scenario order")
        if self.minimum_duration_ms > self.requested_duration_ms:
            raise ValueError("fault matrix minimum duration exceeds request")
        for item in self.cases:
            if item.elapsed_limit_ms != self.elapsed_limit_ms:
                raise ValueError("fault case elapsed limit is inconsistent")
            if (
                item.body_byte_limit is not None
                and item.body_byte_limit >= self.fixture_byte_size
            ):
                raise ValueError("fault case body limit must truncate the fixture")
            if item.actual_status != "failed" and (
                item.output_artifact
                != f"artifacts/stream-fault-{item.case_index:03d}.mkv"
                or item.capture_report_artifact
                != f"reports/stream-fault-{item.case_index:03d}.json"
            ):
                raise ValueError("fault case artifact names are inconsistent")

        captured = sum(item.actual_status != "failed" for item in self.cases)
        ready = sum(item.actual_status == "captured_ready" for item in self.cases)
        not_ready = sum(
            item.actual_status == "captured_not_ready" for item in self.cases
        )
        failed = sum(item.actual_status == "failed" for item in self.cases)
        bounded = sum(item.bounded_completion for item in self.cases)
        expected = sum(item.expectation_met for item in self.cases)
        exercised = sum(item.scenario_exercised for item in self.cases)
        unexpected_ready = sum(
            item.actual_status == "captured_ready"
            and item.expected_status != "captured_ready"
            for item in self.cases
        )
        if (
            self.captured_case_count != captured
            or self.ready_case_count != ready
            or self.not_ready_case_count != not_ready
            or self.failed_case_count != failed
            or captured != ready + not_ready
            or self.bounded_case_count != bounded
            or self.expectation_met_case_count != expected
            or self.scenario_exercised_case_count != exercised
            or self.unexpected_ready_case_count != unexpected_ready
        ):
            raise ValueError("fault matrix counts are inconsistent")
        all_bounded = bounded == self.scenario_count
        all_expected = expected == self.scenario_count
        all_exercised = exercised == self.scenario_count
        if self.all_cases_bounded is not all_bounded:
            raise ValueError("fault matrix bounded result is inconsistent")
        if self.all_expected_outcomes_met is not all_expected:
            raise ValueError("fault matrix expectation result is inconsistent")
        if self.all_scenarios_exercised is not all_exercised:
            raise ValueError("fault matrix execution result is inconsistent")
        if self.controlled_http_fault_matrix_executed is not all_exercised:
            raise ValueError("controlled HTTP fault matrix result is inconsistent")
        gate = bool(
            all_bounded
            and all_expected
            and all_exercised
            and unexpected_ready == 0
        )
        if self.fault_detection_gate_ready is not gate:
            raise ValueError("fault detection gate is inconsistent")
        return self


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


class IndicatorAssessability(StrEnum):
    ASSESSABLE = "assessable"
    NOT_ASSESSABLE = "not_assessable"
    BLOCKED_SEMANTICS = "blocked_semantics"


class IndicatorAssessmentStatus(StrEnum):
    POLICY_NOT_FROZEN = "policy_not_frozen"
    NOT_ASSESSABLE = "not_assessable"
    BLOCKED_SEMANTICS = "blocked_semantics"
    ASSESSED = "assessed"


class IndicatorObservation(ContractModel):
    """A normalized, provenance-bound indicator value before risk scoring."""

    schema_version: str = "1.0"
    observation_id: str
    indicator_id: str
    group: Literal["gait", "posture", "physiology", "sleep"]
    source_modality: Literal["video", "sleep"]
    source_ref: str
    scenario_id: str | None = None
    value: float | str | None = None
    unit: str
    time_range: TimeRange = Field(default_factory=TimeRange)
    assessability: IndicatorAssessability
    quality_status: QualityStatus
    quality_metrics: dict[str, Any] = Field(default_factory=dict)
    sample_count: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _value_matches_assessability(self) -> "IndicatorObservation":
        if self.assessability is IndicatorAssessability.ASSESSABLE:
            if self.value is None:
                raise ValueError("assessable indicator observation requires a value")
            if self.quality_status is QualityStatus.FAIL:
                raise ValueError("assessable indicator observation cannot fail quality")
        elif self.value is not None:
            raise ValueError("unassessable indicator observation must not contain a value")
        return self


class IndicatorAssessment(ContractModel):
    """A policy result kept separate from raw indicator extraction."""

    schema_version: str = "1.0"
    assessment_id: str
    observation_id: str
    indicator_id: str
    status: IndicatorAssessmentStatus
    policy_revision: str | None = None
    policy_digest: str | None = Field(default=None, min_length=64, max_length=64)
    score: int | None = Field(default=None, ge=0, le=3)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _score_requires_frozen_policy(self) -> "IndicatorAssessment":
        frozen = self.status is IndicatorAssessmentStatus.ASSESSED
        if frozen and (self.score is None or not self.policy_revision or not self.policy_digest):
            raise ValueError("assessed indicator requires score and frozen policy binding")
        if not frozen and self.score is not None:
            raise ValueError("non-assessed indicator must not contain a score")
        return self


class IndicatorExtractionReport(ContractModel):
    schema_version: str = "1.0"
    extractor_version: str
    source_modality: Literal["video", "sleep"]
    source_type: SourceType
    evidence_level: EvidenceLevel
    source_ref: str
    observations: list[IndicatorObservation]
    limitations: list[str] = Field(default_factory=list)


class IndicatorSummaryReport(ContractModel):
    """Static indicator report. Global scoring is intentionally unavailable in v1."""

    schema_version: str = "1.0"
    report_version: str
    visibility: Literal["owner_only", "public_evidence"]
    generated_at: datetime = Field(default_factory=utc_now)
    observations: list[IndicatorObservation] = Field(default_factory=list)
    assessments: list[IndicatorAssessment] = Field(default_factory=list)
    indicator_counts: dict[str, int] = Field(default_factory=dict)
    quality_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    global_score: None = None
    fall_candidate_summary: dict[str, int | str | bool | None] | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _public_report_is_value_free(self) -> "IndicatorSummaryReport":
        if self.visibility == "public_evidence" and self.observations:
            raise ValueError("public evidence report must not contain indicator values")
        return self


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


class LongitudinalBucket(StrEnum):
    DAY = "day"
    NIGHT = "night"


class LongitudinalIndicatorSpec(ContractModel):
    indicator_id: str = Field(min_length=1)
    risk_direction: Literal["above", "below", "both"]


class LongitudinalBaselinePolicy(ContractModel):
    """Versioned L1 personal-baseline deviation policy (candidate-only)."""

    schema_version: str = "1.0"
    policy_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    day_start_hour: int = Field(default=6, ge=0, le=23)
    day_end_hour: int = Field(default=18, ge=1, le=24)
    window_days: int = Field(default=28, ge=7)
    min_baseline_samples: int = Field(default=10, ge=1)
    ewma_alpha: float = Field(default=0.3, gt=0.0, le=1.0)
    score_z_thresholds: dict[int, float]
    zero_mad_score: int = Field(default=1, ge=0, le=3)
    indicators: list[LongitudinalIndicatorSpec] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _policy_is_coherent(self) -> "LongitudinalBaselinePolicy":
        if self.day_end_hour <= self.day_start_hour:
            raise ValueError("longitudinal policy day window must be ordered")
        if set(self.score_z_thresholds) != {1, 2, 3}:
            raise ValueError("longitudinal policy requires z thresholds for scores 1..3")
        ordered = [self.score_z_thresholds[score] for score in (1, 2, 3)]
        if any(low >= high for low, high in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("longitudinal policy z thresholds must strictly increase")
        ids = [spec.indicator_id for spec in self.indicators]
        if len(ids) != len(set(ids)):
            raise ValueError("longitudinal policy indicator ids must be unique")
        return self


class PersonalBaseline(ContractModel):
    schema_version: str = "1.0"
    elder_ref: str = Field(min_length=1)
    indicator_id: str = Field(min_length=1)
    bucket: LongitudinalBucket
    computed_at: datetime
    window_days: int = Field(ge=1)
    sample_count: int = Field(ge=0)
    status: Literal["ready", "insufficient_samples"]
    median: float | None = None
    mad: float | None = None
    ewma: float | None = None
    policy_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def _baseline_stats_match_status(self) -> "PersonalBaseline":
        stats = (self.median, self.mad, self.ewma)
        if self.status == "ready":
            if any(value is None for value in stats) or self.sample_count < 1:
                raise ValueError("ready baseline requires statistics and samples")
        elif any(value is not None for value in stats):
            raise ValueError("insufficient baseline must not contain statistics")
        return self


class BaselineDeviationCandidate(ContractModel):
    """Owner-only L1 personal-baseline deviation candidate; not a risk score or alert."""

    schema_version: str = "1.0"
    candidate_id: str = Field(min_length=1)
    elder_ref: str = Field(min_length=1)
    indicator_id: str = Field(min_length=1)
    bucket: LongitudinalBucket
    detected_at: datetime
    direction: Literal["above", "below"]
    z_value: float
    ewma_shift: float | None = None
    score: int = Field(ge=0, le=3)
    policy_revision: str = Field(min_length=1)
    policy_digest: str = Field(min_length=64, max_length=64)
    baseline_sample_count: int = Field(ge=1)
    risk_assessment_emitted: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)


class LongitudinalIngestEntry(ContractModel):
    report_digest: str = Field(min_length=64, max_length=64)
    report_kind: Literal["indicator_extraction", "fall_candidate_prediction_set"]
    status: Literal["ingested", "skipped_duplicate"]
    run_id: str | None = None
    observation_count: int = Field(default=0, ge=0)
    episode_count: int = Field(default=0, ge=0)
    baseline_excluded_count: int = Field(default=0, ge=0)


class LongitudinalIngestReport(ContractModel):
    """Value-free ingest receipt; safe to share as public evidence."""

    schema_version: str = "1.0"
    ingestor_version: str
    elder_ref: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=utc_now)
    entries: list[LongitudinalIngestEntry]
    ingested_count: int = Field(ge=0)
    skipped_duplicate_count: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


class LongitudinalAssessmentReport(ContractModel):
    """L1 personal-baseline assessment. Global scoring is intentionally unavailable."""

    schema_version: str = "1.0"
    report_version: str
    visibility: Literal["owner_only", "public_evidence"]
    elder_ref: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=utc_now)
    policy_revision: str = Field(min_length=1)
    policy_digest: str = Field(min_length=64, max_length=64)
    baselines: list[PersonalBaseline] = Field(default_factory=list)
    deviation_candidates: list[BaselineDeviationCandidate] = Field(default_factory=list)
    observation_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    global_score: None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _public_report_is_value_free(self) -> "LongitudinalAssessmentReport":
        if self.visibility == "public_evidence" and (
            self.baselines or self.deviation_candidates
        ):
            raise ValueError(
                "public longitudinal report must not contain baseline values "
                "or deviation candidates"
            )
        return self
