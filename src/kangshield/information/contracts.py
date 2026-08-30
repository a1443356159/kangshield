"""Strict contracts for the final continuous multidomain product."""

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


class SourceType(StrEnum):
    NETWORK_STREAM = "network_stream"
    FIXTURE = "fixture"


EVIDENCE_RANK = {level: index for index, level in enumerate(EvidenceLevel)}
MAX_EVIDENCE_BY_SOURCE = {
    SourceType.FIXTURE: EvidenceLevel.E1,
    SourceType.NETWORK_STREAM: EvidenceLevel.E2,
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


class TimeRange(ContractModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> "TimeRange":
        if self.start_at is not None and self.end_at is not None:
            if self.end_at < self.start_at:
                raise ValueError("absolute time range is reversed")
        if self.start_ms is not None and self.end_ms is not None:
            if self.end_ms < self.start_ms:
                raise ValueError("relative time range is reversed")
        return self


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


class SpeechSegment(ContractModel):
    """Owner-only recognized speech over one selected in-memory window."""

    schema_version: str = "1.0"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    language: str
    confidence: float | None = None
    transcript_ref: str | None = None
    finalized: bool = True

    @model_validator(mode="after")
    def _ordered(self) -> "SpeechSegment":
        if self.end_ms < self.start_ms:
            raise ValueError("speech segment end precedes start")
        return self


class FallFeatureConfig(ContractModel):
    schema_version: str = "1.0"
    feature_version: str = "fall-motion-features-v0.1.0"
    selection_strategy: Literal["largest_bbox"] = "largest_bbox"
    expected_keypoint_layout: Literal["COCO-17"] = "COCO-17"
    expected_keypoint_count: int = Field(default=17, ge=1)
    required_keypoint_indices: list[int] = Field(
        default_factory=lambda: [5, 6, 11, 12], min_length=1
    )
    keypoint_confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    keypoint_visible_ratio_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    torso_horizontal_angle_max_deg: float = Field(default=45.0, ge=0.0, le=90.0)
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
    def _valid_layout_and_windows(self) -> "FallFeatureConfig":
        if self.expected_keypoint_count != 17:
            raise ValueError("COCO-17 layout requires exactly 17 keypoints")
        if self.required_keypoint_indices != [5, 6, 11, 12]:
            raise ValueError("COCO-17 torso geometry requires indices 5, 6, 11, 12")
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
    max_center_displacement_diagonal_ratio: float | None = Field(default=None, ge=0.0)
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
    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=3)
    fixture: bool
    review_status: Literal["fixture_only", "e1_exploratory_frozen"] = "fixture_only"
    target_event_label: Literal["simulated_fall"] = "simulated_fall"
    input_fall_feature_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    def _frozen_rules_are_complete(self) -> "FallEventCandidatePolicy":
        rules = (self.transition_rule, self.settled_rule, self.state_machine)
        if self.fixture:
            if self.review_status != "fixture_only":
                raise ValueError("fixture candidate policy must remain fixture_only")
            if any(rule is None for rule in rules) and any(
                rule is not None for rule in rules
            ):
                raise ValueError("fixture candidate policy rules must be all or none")
        else:
            if self.review_status != "e1_exploratory_frozen":
                raise ValueError("non-fixture candidate policy must be E1 frozen")
            if any(rule is None for rule in rules):
                raise ValueError("non-fixture candidate policy requires all rules")
        if self.transition_rule and self.settled_rule:
            if (
                self.transition_rule.minimum_horizontal_duration_ms
                > self.settled_rule.minimum_horizontal_duration_ms
            ):
                raise ValueError("transition duration cannot exceed settled fallback")
        return self


class FallEventCandidateEpisode(ContractModel):
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
    def _ordered(self) -> "FallEventCandidateEpisode":
        if self.end_ms <= self.start_ms:
            raise ValueError("candidate episode end must be after start")
        if not self.start_ms <= self.detected_at_ms <= self.end_ms:
            raise ValueError("candidate detection must be inside the episode")
        return self


class EdgeKeyWindow(ContractModel):
    schema_version: str = "1.0"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    modalities: list[Literal["video", "audio"]] = Field(min_length=1)
    reasons: list[Literal["baseline", "motion", "audio_activity"]] = Field(
        min_length=1
    )
    peak_motion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    peak_audio_rms: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _bounded(self) -> "EdgeKeyWindow":
        if self.end_ms <= self.start_ms:
            raise ValueError("edge key window end must follow start")
        if len(set(self.modalities)) != len(self.modalities):
            raise ValueError("edge key window modalities must be unique")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("edge key window reasons must be unique")
        return self


class EdgeSegmentAudit(ContractModel):
    """Path-free receipt for one in-memory segment."""

    schema_version: str = "1.0"
    segment_id: str = Field(min_length=1, max_length=96)
    device_ref: str = Field(min_length=1, max_length=64)
    segment_started_at: datetime
    segment_ended_at: datetime
    status: Literal["completed", "partial", "failed"]
    failure_code: str | None = Field(default=None, max_length=64)
    cloud_recording_ref: str = Field(min_length=1, max_length=128)
    cloud_recording_is_source_of_truth: Literal[True] = True
    selector_revision: str = Field(min_length=1, max_length=96)
    selector_digest: str = Field(min_length=64, max_length=64)
    endpoint_value_persisted: Literal[False] = False
    endpoint_digest_persisted: Literal[False] = False
    raw_video_persisted: Literal[False] = False
    raw_audio_persisted: Literal[False] = False
    screened_video_seconds: float = Field(default=0.0, ge=0.0)
    screened_audio_seconds: float = Field(default=0.0, ge=0.0)
    selected_pose_seconds: float = Field(default=0.0, ge=0.0)
    selected_asr_seconds: float = Field(default=0.0, ge=0.0)
    screened_frame_count: int = Field(default=0, ge=0)
    selected_frame_count: int = Field(default=0, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    key_windows: list[EdgeKeyWindow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> "EdgeSegmentAudit":
        if self.segment_ended_at <= self.segment_started_at:
            raise ValueError("edge segment end must follow start")
        duration = (self.segment_ended_at - self.segment_started_at).total_seconds()
        tolerance = 1.0
        if self.screened_video_seconds > duration + tolerance:
            raise ValueError("screened video exceeds segment duration")
        if self.screened_audio_seconds > duration + tolerance:
            raise ValueError("screened audio exceeds segment duration")
        if self.selected_pose_seconds > self.screened_video_seconds + tolerance:
            raise ValueError("selected pose exceeds screened video")
        if self.selected_asr_seconds > self.screened_audio_seconds + tolerance:
            raise ValueError("selected ASR exceeds screened audio")
        if self.selected_frame_count > self.screened_frame_count:
            raise ValueError("selected frame count exceeds screened frame count")
        if self.status == "completed" and self.failure_code is not None:
            raise ValueError("completed edge segment cannot carry a failure code")
        if self.status != "completed" and not self.failure_code:
            raise ValueError("partial or failed segment requires a failure code")
        segment_ms = round(duration * 1000)
        if any(window.end_ms > segment_ms + 1000 for window in self.key_windows):
            raise ValueError("edge key window exceeds segment bounds")
        return self


class RiskDomain(StrEnum):
    FALL = "fall"
    MENTAL_WELLBEING = "mental_wellbeing"
    FRAUD = "fraud"


class DomainRiskStatus(StrEnum):
    ASSESSED = "assessed"
    INSUFFICIENT_DATA = "insufficient_data"
    DATA_STALE = "data_stale"
    MODEL_UNAVAILABLE = "model_unavailable"


class CandidateReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class DomainRiskAssessment(ContractModel):
    """One pilot rule assessment; the score is never a probability."""

    schema_version: str = "2.0"
    domain: RiskDomain
    score: int | None = Field(default=None, ge=0, le=3)
    status: DomainRiskStatus
    window: TimeRange
    data_coverage: dict[str, int | float | str | bool | None] = Field(
        default_factory=dict
    )
    evidence_summary: list[str] = Field(default_factory=list)
    policy_revision: str = Field(min_length=1)
    policy_digest: str = Field(min_length=64, max_length=64)
    policy_summary: str = Field(min_length=1)
    pilot_unvalidated: Literal[True] = True
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _score_matches_status(self) -> "DomainRiskAssessment":
        if self.score is None:
            if self.status is DomainRiskStatus.ASSESSED:
                raise ValueError("assessed domain requires a 0-3 score")
            if not self.limitations:
                raise ValueError("null domain score requires a limitation reason")
        elif self.status is not DomainRiskStatus.ASSESSED:
            raise ValueError("non-assessed domain must have a null score")
        return self


class DomainCandidate(ContractModel):
    schema_version: str = "2.0"
    candidate_id: str = Field(min_length=1)
    domain: RiskDomain
    category: str = Field(min_length=1)
    occurred_at: datetime
    evidence_refs: list[str] = Field(min_length=1)
    evidence_summary: list[str] = Field(default_factory=list)
    quality: float | None = Field(default=None, ge=0, le=1)
    review_status: CandidateReviewStatus = CandidateReviewStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)


class CandidateReviewDecision(ContractModel):
    schema_version: str = "2.0"
    candidate_id: str = Field(min_length=1)
    decision: ReviewDecision
    decided_at: datetime = Field(default_factory=utc_now)
    operator: str = Field(min_length=1, max_length=64)
    owner_note: str | None = Field(default=None, max_length=2000)


class WellbeingCheckinSubmission(ContractModel):
    schema_version: str = "1.0"
    answers: list[int] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def _valid_answers(self) -> "WellbeingCheckinSubmission":
        if any(answer < 0 or answer > 5 for answer in self.answers):
            raise ValueError("WHO-5 answers must be integers from 0 through 5")
        return self


class MultidomainSnapshotReport(ContractModel):
    schema_version: str = "2.0"
    report_version: str
    generated_at: datetime = Field(default_factory=utc_now)
    visibility: Literal["owner_only", "public_evidence"] = "owner_only"
    assessments: list[DomainRiskAssessment]
    data_freshness: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
    timeline: list[DomainCandidate] = Field(default_factory=list)
    quality_status: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
    global_score: None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _exactly_three_domains(self) -> "MultidomainSnapshotReport":
        domains = [assessment.domain for assessment in self.assessments]
        if len(domains) != 3 or set(domains) != set(RiskDomain):
            raise ValueError("snapshot requires each of the three risk domains once")
        if self.visibility == "public_evidence" and self.timeline:
            raise ValueError("public snapshot must not expose candidate timeline")
        return self
