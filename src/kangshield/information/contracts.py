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
    m2c_ready_for_review: bool = False
    decision: str
    quality_status: QualityStatus
    raw_paths_persisted: Literal[False] = False
    identity_refs_persisted: Literal[False] = False
    annotation_windows_persisted: Literal[False] = False
    health_values_persisted: Literal[False] = False
    issues: list[QualityIssue] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


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
