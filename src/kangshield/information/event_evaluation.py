from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path, PurePosixPath
from statistics import mean, median
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    FallCandidatePredictionClip,
    FallCandidatePredictionEvent,
    FallCandidatePredictionSet,
    FallEventAnnotationAgreement,
    FallEventCandidatePolicy,
    FallEventCaseEvaluation,
    FallEventEvaluationReadinessReport,
    FallEventVariantEvaluation,
    M2cCaptureReadinessReport,
    Modality,
    PrivacyLevel,
    QualityIssue,
    QualityStatus,
    RunManifest,
    RunStatus,
    Severity,
    SourceAsset,
    SourceType,
    ensure_source_evidence_compatible,
)
from .m2c_capture import M2cEventContext, load_m2c_event_context
from .privacy import safe_local_uri, sha256_file


ASSESSOR_VERSION = "g4-event-evaluation-readiness-v0.1.0"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _require_aware(value: datetime, *, field: str) -> None:
    if value.utcoffset() is None:
        raise ValueError(f"{field} must include an explicit timezone")


class _FileReference(_StrictModel):
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(gt=0)


class _PredictionBinding(_StrictModel):
    variant_id: str = Field(min_length=1)
    candidate_events: _FileReference
    source_run_manifest: _FileReference


class _EvaluationBundle(_StrictModel):
    schema_version: Literal["1.0"]
    evaluation_id: str = Field(min_length=3)
    fixture: bool
    capture_manifest: _FileReference
    capture_readiness_report: _FileReference
    capture_assessment_run_manifest: _FileReference
    candidate_generator_policy: _FileReference
    annotation_sets: list[_FileReference] = Field(min_length=1)
    adjudication: _FileReference
    predictions: list[_PredictionBinding] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "_EvaluationBundle":
        variants = [item.variant_id for item in self.predictions]
        if len(variants) != len(set(variants)):
            raise ValueError("prediction variants must be unique")
        annotation_paths = [item.relative_path for item in self.annotation_sets]
        if len(annotation_paths) != len(set(annotation_paths)):
            raise ValueError("annotation references must be unique")
        return self


class _Interval(_StrictModel):
    label: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    certainty: Literal["certain", "uncertain"]

    @model_validator(mode="after")
    def validate_interval(self) -> "_Interval":
        if self.end_ms <= self.start_ms:
            raise ValueError("event interval end must be after start")
        return self


class _AnnotatedClip(_StrictModel):
    scenario_id: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    windows: list[_Interval] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_windows(self) -> "_AnnotatedClip":
        if any(window.end_ms > self.duration_ms for window in self.windows):
            raise ValueError("annotation interval exceeds clip duration")
        for label in {window.label for window in self.windows}:
            ordered = sorted(
                (window.start_ms, window.end_ms)
                for window in self.windows
                if window.label == label
            )
            if any(
                next_start < current_end
                for (_, current_end), (next_start, _) in zip(
                    ordered,
                    ordered[1:],
                    strict=False,
                )
            ):
                raise ValueError("same-label annotation intervals cannot overlap")
        return self


class _AnnotationSet(_StrictModel):
    schema_version: Literal["1.0"]
    annotation_set_id: str = Field(min_length=3)
    annotator_ref: str = Field(min_length=3)
    independent: Literal[True]
    capture_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_at: datetime
    clips: list[_AnnotatedClip] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_annotation_set(self) -> "_AnnotationSet":
        _require_aware(self.frozen_at, field="annotation frozen_at")
        ids = [clip.scenario_id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("annotation scenario ids must be unique")
        return self


class _Adjudication(_StrictModel):
    schema_version: Literal["1.0"]
    adjudication_id: str = Field(min_length=3)
    adjudicator_ref: str = Field(min_length=3)
    capture_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    input_annotation_sha256s: list[str] = Field(min_length=1)
    frozen_at: datetime
    all_disagreements_resolved: Literal[True]
    resolved_disagreement_count: int = Field(ge=0)
    clips: list[_AnnotatedClip] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_adjudication(self) -> "_Adjudication":
        _require_aware(self.frozen_at, field="adjudication frozen_at")
        if any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in self.input_annotation_sha256s
        ):
            raise ValueError("adjudication annotation digests must be SHA-256")
        if len(self.input_annotation_sha256s) != len(
            set(self.input_annotation_sha256s)
        ):
            raise ValueError("adjudication annotation digests must be unique")
        ids = [clip.scenario_id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("adjudication scenario ids must be unique")
        return self


class _RequiredVariant(_StrictModel):
    variant_id: str = Field(min_length=1)
    model_policy_sha256: str = Field(pattern=SHA256_PATTERN)


class _EvaluationPolicy(_StrictModel):
    schema_version: Literal["1.0"]
    policy_version: str = Field(min_length=1)
    target_event_label: Literal["simulated_fall"]
    compared_labels: list[str] = Field(min_length=1)
    required_hard_negative_labels: list[str] = Field(min_length=1)
    minimum_annotation_sets: int = Field(ge=2)
    interval_iou_threshold: float = Field(gt=0.0, le=1.0)
    minimum_pairwise_interval_f1: float = Field(ge=0.0, le=1.0)
    minimum_pairwise_target_f1: float = Field(ge=0.0, le=1.0)
    maximum_mean_absolute_target_onset_difference_ms: float = Field(ge=0.0)
    maximum_event_match_early_ms: int = Field(ge=0)
    maximum_event_match_late_ms: int = Field(ge=0)
    minimum_clip_count: int = Field(ge=1)
    minimum_positive_event_count: int = Field(ge=1)
    minimum_negative_clip_count: int = Field(ge=1)
    expected_capture_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_fall_feature_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_stage: str = Field(min_length=1)
    required_variants: list[_RequiredVariant] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy(self) -> "_EvaluationPolicy":
        if self.target_event_label not in self.compared_labels:
            raise ValueError("target event label must be compared")
        if not set(self.required_hard_negative_labels).issubset(
            self.compared_labels
        ):
            raise ValueError("hard-negative labels must be compared")
        if len(self.compared_labels) != len(set(self.compared_labels)):
            raise ValueError("compared labels must be unique")
        variants = [item.variant_id for item in self.required_variants]
        if len(variants) != len(set(variants)):
            raise ValueError("required event variants must be unique")
        return self


@dataclass(frozen=True)
class FallEventEvaluationAssessment:
    assets: list[SourceAsset]
    report: FallEventEvaluationReadinessReport


def _load_json(path: Path, model: type[ConfigModel], *, kind: str) -> ConfigModel:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{kind} could not be read as JSON") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"{kind} schema validation failed") from error


def _safe_bundle_path(bundle_root: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in relative_path
    ):
        raise ValueError("event bundle reference must be a normalized relative path")
    root = bundle_root.resolve()
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("event bundle reference escapes the bundle directory")
    return resolved


def _verified_path(
    bundle_root: Path,
    reference: _FileReference,
    *,
    kind: str,
) -> Path:
    path = _safe_bundle_path(bundle_root, reference.relative_path)
    if not path.is_file():
        raise ValueError(f"referenced {kind} file is missing")
    if path.stat().st_size != reference.byte_size:
        raise ValueError(f"referenced {kind} byte size differs from the bundle")
    if sha256_file(path) != reference.sha256:
        raise ValueError(f"referenced {kind} digest differs from the bundle")
    return path


def _asset(
    path: Path,
    *,
    modality: Modality,
    source_type: SourceType,
    evidence_level: EvidenceLevel,
) -> SourceAsset:
    digest = sha256_file(path)
    return SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=modality,
        source_type=source_type,
        evidence_level=evidence_level,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
        metadata={
            "filename_suffix": path.suffix.lower(),
            "source_path_persisted": False,
        },
    )


def _validate_clip_set(
    clips: list[_AnnotatedClip] | list[FallCandidatePredictionClip],
    context: M2cEventContext,
    *,
    kind: str,
) -> None:
    expected = {
        clip.scenario_id: clip.duration_ms
        for clip in context.clips
    }
    observed = {clip.scenario_id: clip.duration_ms for clip in clips}
    if observed != expected:
        raise ValueError(f"{kind} clip coverage or duration differs from capture")


def _validate_labels(clips: list[_AnnotatedClip], policy: _EvaluationPolicy) -> None:
    allowed = set(policy.compared_labels)
    if any(window.label not in allowed for clip in clips for window in clip.windows):
        raise ValueError("event annotations contain a label outside policy")


def _label_count(clips: list[_AnnotatedClip], label: str) -> int:
    return sum(
        window.label == label
        for clip in clips
        for window in clip.windows
    )


def _interval_iou(left: _Interval, right: _Interval) -> float:
    intersection = max(0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms))
    union = max(left.end_ms, right.end_ms) - min(left.start_ms, right.start_ms)
    return intersection / union if union else 0.0


def _match_intervals(
    left: list[_Interval],
    right: list[_Interval],
    *,
    threshold: float,
) -> list[tuple[int, int]]:
    candidates = []
    for left_index, left_window in enumerate(left):
        for right_index, right_window in enumerate(right):
            iou = _interval_iou(left_window, right_window)
            if iou >= threshold:
                candidates.append((-iou, left_index, right_index))
    matches: list[tuple[int, int]] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    for _, left_index, right_index in sorted(candidates):
        if left_index in used_left or right_index in used_right:
            continue
        used_left.add(left_index)
        used_right.add(right_index)
        matches.append((left_index, right_index))
    return matches


def _agreement(
    left: _AnnotationSet,
    right: _AnnotationSet,
    *,
    pair_ref: str,
    policy: _EvaluationPolicy,
) -> FallEventAnnotationAgreement:
    right_by_clip = {clip.scenario_id: clip for clip in right.clips}
    left_count = 0
    right_count = 0
    matched_count = 0
    target_left_count = 0
    target_right_count = 0
    target_matched_count = 0
    target_onset_differences: list[float] = []
    for left_clip in left.clips:
        right_clip = right_by_clip[left_clip.scenario_id]
        for label in policy.compared_labels:
            left_windows = [
                window for window in left_clip.windows if window.label == label
            ]
            right_windows = [
                window for window in right_clip.windows if window.label == label
            ]
            matches = _match_intervals(
                left_windows,
                right_windows,
                threshold=policy.interval_iou_threshold,
            )
            left_count += len(left_windows)
            right_count += len(right_windows)
            matched_count += len(matches)
            if label == policy.target_event_label:
                target_left_count += len(left_windows)
                target_right_count += len(right_windows)
                target_matched_count += len(matches)
                target_onset_differences.extend(
                    abs(
                        left_windows[left_index].start_ms
                        - right_windows[right_index].start_ms
                    )
                    for left_index, right_index in matches
                )
    total = left_count + right_count
    interval_f1 = 1.0 if total == 0 else 2 * matched_count / total
    target_total = target_left_count + target_right_count
    target_f1 = (
        1.0 if target_total == 0 else 2 * target_matched_count / target_total
    )
    mean_onset = (
        float(mean(target_onset_differences))
        if target_onset_differences
        else None
    )
    maximum_onset = (
        float(max(target_onset_differences))
        if target_onset_differences
        else None
    )
    passes = (
        interval_f1 >= policy.minimum_pairwise_interval_f1
        and target_f1 >= policy.minimum_pairwise_target_f1
        and mean_onset is not None
        and mean_onset
        <= policy.maximum_mean_absolute_target_onset_difference_ms
    )
    return FallEventAnnotationAgreement(
        pair_ref=pair_ref,
        compared_label_count=len(policy.compared_labels),
        left_window_count=left_count,
        right_window_count=right_count,
        matched_window_count=matched_count,
        unmatched_window_count=left_count + right_count - 2 * matched_count,
        interval_f1=round(interval_f1, 6),
        target_left_window_count=target_left_count,
        target_right_window_count=target_right_count,
        target_matched_window_count=target_matched_count,
        target_unmatched_window_count=(
            target_left_count + target_right_count - 2 * target_matched_count
        ),
        target_interval_f1=round(target_f1, 6),
        matched_target_onset_count=len(target_onset_differences),
        mean_absolute_target_onset_difference_ms=(
            round(mean_onset, 3) if mean_onset is not None else None
        ),
        maximum_absolute_target_onset_difference_ms=(
            round(maximum_onset, 3) if maximum_onset is not None else None
        ),
        passes=passes,
    )


def _score(value: int, total: int) -> float:
    return 1.0 if total == 0 else value / total


def _f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (
        precision + recall
    )


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _match_candidates(
    ground_truth: list[_Interval],
    candidates: list[FallCandidatePredictionEvent],
    *,
    max_early_ms: int,
    max_late_ms: int,
) -> list[tuple[int, int, float]]:
    possible: list[tuple[float, int, int]] = []
    for truth_index, truth in enumerate(ground_truth):
        for candidate_index, candidate in enumerate(candidates):
            if (
                truth.start_ms - max_early_ms
                <= candidate.detected_at_ms
                <= truth.end_ms + max_late_ms
            ):
                delay = float(candidate.detected_at_ms - truth.start_ms)
                possible.append((abs(delay), truth_index, candidate_index))
    matches: list[tuple[int, int, float]] = []
    used_truth: set[int] = set()
    used_candidates: set[int] = set()
    for _, truth_index, candidate_index in sorted(possible):
        if truth_index in used_truth or candidate_index in used_candidates:
            continue
        used_truth.add(truth_index)
        used_candidates.add(candidate_index)
        delay = float(
            candidates[candidate_index].detected_at_ms
            - ground_truth[truth_index].start_ms
        )
        matches.append((truth_index, candidate_index, delay))
    return matches


def _variant_evaluation(
    prediction: FallCandidatePredictionSet,
    source_run: RunManifest,
    adjudication: _Adjudication,
    context: M2cEventContext,
    policy: _EvaluationPolicy,
) -> FallEventVariantEvaluation:
    truth_by_clip = {clip.scenario_id: clip for clip in adjudication.clips}
    prediction_by_clip = {clip.scenario_id: clip for clip in prediction.clips}
    cases: list[FallEventCaseEvaluation] = []
    all_delays: list[float] = []
    for clip in context.clips:
        truth = [
            window
            for window in truth_by_clip[clip.scenario_id].windows
            if window.label == policy.target_event_label
        ]
        candidates = prediction_by_clip[clip.scenario_id].candidates
        matches = _match_candidates(
            truth,
            candidates,
            max_early_ms=policy.maximum_event_match_early_ms,
            max_late_ms=policy.maximum_event_match_late_ms,
        )
        delays = [delay for _, _, delay in matches]
        all_delays.extend(delays)
        true_positive = len(matches)
        false_positive = len(candidates) - true_positive
        false_negative = len(truth) - true_positive
        precision = _score(true_positive, len(candidates))
        recall = _score(true_positive, len(truth))
        case_ref = "case_" + hashlib.sha256(
            f"{context.manifest_sha256}:{clip.scenario_id}".encode("utf-8")
        ).hexdigest()[:16]
        cases.append(
            FallEventCaseEvaluation(
                case_ref=case_ref,
                scenario_id=clip.scenario_id,
                scenario=clip.scenario,
                duration_ms=clip.duration_ms,
                ground_truth_event_count=len(truth),
                candidate_event_count=len(candidates),
                true_positive_count=true_positive,
                false_positive_count=false_positive,
                false_negative_count=false_negative,
                precision=round(precision, 6),
                recall=round(recall, 6),
                f1=round(_f1(precision, recall), 6),
                negative_case=not truth,
                false_activation=not truth and bool(candidates),
                detection_delay_count=len(delays),
                mean_detection_delay_ms=(
                    round(float(mean(delays)), 3) if delays else None
                ),
                median_detection_delay_ms=(
                    round(float(median(delays)), 3) if delays else None
                ),
            )
        )
    exposure_ms = sum(case.duration_ms for case in cases)
    ground_truth_count = sum(case.ground_truth_event_count for case in cases)
    candidate_count = sum(case.candidate_event_count for case in cases)
    true_positive_count = sum(case.true_positive_count for case in cases)
    false_positive_count = sum(case.false_positive_count for case in cases)
    false_negative_count = sum(case.false_negative_count for case in cases)
    negative_clip_count = sum(case.negative_case for case in cases)
    false_activation_clip_count = sum(case.false_activation for case in cases)
    precision = _score(true_positive_count, candidate_count)
    recall = _score(true_positive_count, ground_truth_count)
    p95 = _percentile(all_delays, 0.95)
    return FallEventVariantEvaluation(
        variant_id=prediction.variant_id,
        source_run_id=source_run.run_id,
        source_code_version=source_run.code_version,
        source_evidence_level=source_run.evidence_level,
        source_run_completed=source_run.status is RunStatus.COMPLETED,
        source_run_clean=not source_run.code_dirty,
        model_policy_sha256=prediction.model_policy_sha256,
        fall_feature_policy_sha256=prediction.fall_feature_policy_sha256,
        candidate_generator_policy_sha256=(
            prediction.candidate_generator_policy_sha256
        ),
        clip_count=len(cases),
        exposure_ms=exposure_ms,
        ground_truth_event_count=ground_truth_count,
        candidate_event_count=candidate_count,
        true_positive_count=true_positive_count,
        false_positive_count=false_positive_count,
        false_negative_count=false_negative_count,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(_f1(precision, recall), 6),
        false_activations_per_hour=round(
            false_positive_count * 3_600_000 / exposure_ms,
            6,
        ),
        negative_clip_count=negative_clip_count,
        false_activation_clip_count=false_activation_clip_count,
        negative_clip_false_activation_rate=round(
            _score(false_activation_clip_count, negative_clip_count),
            6,
        ),
        detection_delay_count=len(all_delays),
        mean_detection_delay_ms=(
            round(float(mean(all_delays)), 3) if all_delays else None
        ),
        median_detection_delay_ms=(
            round(float(median(all_delays)), 3) if all_delays else None
        ),
        p95_detection_delay_ms=round(p95, 3) if p95 is not None else None,
        minimum_detection_delay_ms=(
            round(min(all_delays), 3) if all_delays else None
        ),
        maximum_detection_delay_ms=(
            round(max(all_delays), 3) if all_delays else None
        ),
        cases=cases,
        limitations=[
            "candidate_events_are_scored_not_generated_by_this_evaluator",
            "false_activations_per_hour_uses_total_held_out_clip_exposure",
            "matching_is_one_to_one_on_candidate_detection_time",
        ],
    )


def _gate_issue(code: str, message: str, *, error: bool = False) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=Severity.ERROR if error else Severity.WARNING,
        message=message,
    )


def _validate_run_configuration(
    run: RunManifest,
    expected: dict[str, str],
    *,
    kind: str,
) -> None:
    if any(run.configuration.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{kind} run configuration disagrees with frozen inputs")


def assess_fall_event_evaluation(
    bundle_path: Path,
    *,
    policy_path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
) -> FallEventEvaluationAssessment:
    """Score held-out candidate events without producing risk or alert outputs."""

    ensure_source_evidence_compatible(source_type, evidence_level)
    bundle_path = Path(bundle_path)
    policy_path = Path(policy_path)
    if not bundle_path.is_file():
        raise FileNotFoundError("event evaluation bundle not found")
    if not policy_path.is_file():
        raise FileNotFoundError("event evaluation policy not found")
    bundle = _load_json(bundle_path, _EvaluationBundle, kind="event bundle")
    policy = _load_json(policy_path, _EvaluationPolicy, kind="event policy")
    if bundle.fixture != (source_type is SourceType.FIXTURE):
        raise ValueError("bundle fixture marker disagrees with source type")
    bundle_root = bundle_path.parent
    bundle_sha256 = sha256_file(bundle_path)
    policy_sha256 = sha256_file(policy_path)
    assets = [
        _asset(
            bundle_path,
            modality=Modality.MULTIMODAL,
            source_type=source_type,
            evidence_level=evidence_level,
        ),
        _asset(
            policy_path,
            modality=Modality.DEVICE_SNAPSHOT,
            source_type=source_type,
            evidence_level=evidence_level,
        ),
    ]

    capture_manifest_path = _verified_path(
        bundle_root,
        bundle.capture_manifest,
        kind="capture manifest",
    )
    capture_readiness_path = _verified_path(
        bundle_root,
        bundle.capture_readiness_report,
        kind="capture readiness report",
    )
    capture_run_path = _verified_path(
        bundle_root,
        bundle.capture_assessment_run_manifest,
        kind="capture assessment run",
    )
    candidate_policy_path = _verified_path(
        bundle_root,
        bundle.candidate_generator_policy,
        kind="candidate generator policy",
    )
    for path, modality in (
        (capture_manifest_path, Modality.DEVICE_SNAPSHOT),
        (capture_readiness_path, Modality.MULTIMODAL),
        (capture_run_path, Modality.DEVICE_SNAPSHOT),
        (candidate_policy_path, Modality.DEVICE_SNAPSHOT),
    ):
        assets.append(
            _asset(
                path,
                modality=modality,
                source_type=source_type,
                evidence_level=evidence_level,
            )
        )

    context = load_m2c_event_context(capture_manifest_path)
    capture_readiness = _load_json(
        capture_readiness_path,
        M2cCaptureReadinessReport,
        kind="capture readiness report",
    )
    capture_run = _load_json(
        capture_run_path,
        RunManifest,
        kind="capture assessment run",
    )
    candidate_policy = _load_json(
        candidate_policy_path,
        FallEventCandidatePolicy,
        kind="candidate generator policy",
    )
    candidate_policy_sha256 = sha256_file(candidate_policy_path)
    if candidate_policy.fixture != bundle.fixture:
        raise ValueError("candidate policy fixture marker disagrees with bundle")
    if candidate_policy.target_event_label != policy.target_event_label:
        raise ValueError("candidate policy target differs from evaluation policy")
    if (
        candidate_policy.input_fall_feature_policy_sha256
        != policy.expected_fall_feature_policy_sha256
    ):
        raise ValueError("candidate policy input feature digest differs from policy")
    if capture_readiness.manifest_sha256 != context.manifest_sha256:
        raise ValueError("capture readiness report refers to another manifest")
    if capture_readiness.capture_ref != context.capture_ref:
        raise ValueError("capture readiness report capture ref is inconsistent")
    if capture_readiness.policy_sha256 != policy.expected_capture_policy_sha256:
        raise ValueError("capture readiness policy differs from event policy")
    if (
        capture_readiness.template_only != context.template_only
        or capture_readiness.synthetic != context.synthetic
    ):
        raise ValueError("capture readiness fixture facts disagree with manifest")
    readiness_clips = {
        item.scenario_id: item.clip_ref for item in capture_readiness.clips
    }
    context_clips = {item.scenario_id: item.clip_ref for item in context.clips}
    if (
        len(readiness_clips) != len(capture_readiness.clips)
        or readiness_clips != context_clips
    ):
        raise ValueError("capture readiness clip index differs from manifest")
    capture_readiness_sha256 = sha256_file(capture_readiness_path)
    _validate_run_configuration(
        capture_run,
        {
            "capture_manifest_sha256": context.manifest_sha256,
            "capture_readiness_report_sha256": capture_readiness_sha256,
        },
        kind="capture assessment",
    )
    if capture_run.stage != "v1-m2c-capture-readiness":
        raise ValueError("capture assessment run stage is invalid")

    annotation_paths = [
        _verified_path(bundle_root, reference, kind="annotation set")
        for reference in bundle.annotation_sets
    ]
    annotations = [
        _load_json(path, _AnnotationSet, kind="annotation set")
        for path in annotation_paths
    ]
    for path in annotation_paths:
        assets.append(
            _asset(
                path,
                modality=Modality.VIDEO,
                source_type=source_type,
                evidence_level=evidence_level,
            )
        )
    annotation_ids = [item.annotation_set_id for item in annotations]
    annotator_refs = [item.annotator_ref for item in annotations]
    if len(annotation_ids) != len(set(annotation_ids)):
        raise ValueError("annotation set ids must be unique")
    if len(annotator_refs) != len(set(annotator_refs)):
        raise ValueError("independent annotation sets require unique annotators")
    annotation_label_coverage = True
    for annotation in annotations:
        if annotation.capture_manifest_sha256 != context.manifest_sha256:
            raise ValueError("annotation set refers to another capture manifest")
        _validate_clip_set(annotation.clips, context, kind="annotation")
        _validate_labels(annotation.clips, policy)
        if not context.captured_end_at <= annotation.frozen_at <= context.labels_frozen_at:
            raise ValueError("annotation freeze time violates held-out order")
        annotation_label_coverage = annotation_label_coverage and (
            _label_count(annotation.clips, policy.target_event_label)
            >= policy.minimum_positive_event_count
            and all(
                _label_count(annotation.clips, label) >= 1
                for label in policy.required_hard_negative_labels
            )
        )
    annotations_complete = (
        len(annotations) >= policy.minimum_annotation_sets
        and annotation_label_coverage
    )
    agreements = [
        _agreement(
            left,
            right,
            pair_ref=f"pair_{index:03d}",
            policy=policy,
        )
        for index, (left, right) in enumerate(combinations(annotations, 2), start=1)
    ]
    agreement_gate_passed = bool(agreements) and all(
        agreement.passes for agreement in agreements
    )

    adjudication_path = _verified_path(
        bundle_root,
        bundle.adjudication,
        kind="adjudication",
    )
    assets.append(
        _asset(
            adjudication_path,
            modality=Modality.VIDEO,
            source_type=source_type,
            evidence_level=evidence_level,
        )
    )
    adjudication = _load_json(
        adjudication_path,
        _Adjudication,
        kind="adjudication",
    )
    if adjudication.capture_manifest_sha256 != context.manifest_sha256:
        raise ValueError("adjudication refers to another capture manifest")
    if sorted(adjudication.input_annotation_sha256s) != sorted(
        sha256_file(path) for path in annotation_paths
    ):
        raise ValueError("adjudication inputs differ from annotation sets")
    if any(adjudication.frozen_at < item.frozen_at for item in annotations):
        raise ValueError("adjudication was frozen before an annotation set")
    if adjudication.frozen_at > context.labels_frozen_at:
        raise ValueError("adjudication was frozen after held-out labels")
    _validate_clip_set(adjudication.clips, context, kind="adjudication")
    _validate_labels(adjudication.clips, policy)
    ground_truth_event_count = _label_count(
        adjudication.clips,
        policy.target_event_label,
    )
    hard_negative_coverage = all(
        _label_count(adjudication.clips, label) >= 1
        for label in policy.required_hard_negative_labels
    )
    negative_clip_count = sum(
        not any(
            window.label == policy.target_event_label for window in clip.windows
        )
        for clip in adjudication.clips
    )
    adjudication_complete = (
        adjudication.all_disagreements_resolved
        and hard_negative_coverage
        and all(
            window.certainty == "certain"
            for clip in adjudication.clips
            for window in clip.windows
        )
    )
    minimum_data_gate_passed = (
        len(context.clips) >= policy.minimum_clip_count
        and ground_truth_event_count >= policy.minimum_positive_event_count
        and negative_clip_count >= policy.minimum_negative_clip_count
        and hard_negative_coverage
    )

    expected_variants = {
        item.variant_id: item.model_policy_sha256
        for item in policy.required_variants
    }
    bundle_variants = {item.variant_id for item in bundle.predictions}
    if bundle_variants != set(expected_variants):
        raise ValueError("event bundle variants differ from evaluation policy")
    capture_model_policies = dict(context.model_policy_sha256s)
    if any(
        capture_model_policies.get(variant_id) != model_digest
        for variant_id, model_digest in expected_variants.items()
    ):
        raise ValueError("capture held-out model policies differ from event policy")

    provenance_gate_passed = True
    issues: list[QualityIssue] = []
    capture_run_times_valid = (
        capture_run.finished_at is not None
        and capture_run.started_at.utcoffset() is not None
        and capture_run.finished_at.utcoffset() is not None
        and capture_run.started_at >= context.labels_frozen_at
        and capture_run.finished_at >= capture_run.started_at
    )
    if (
        capture_run.status is not RunStatus.COMPLETED
        or capture_run.code_dirty
        or capture_run.code_version == "unknown"
        or capture_run.evidence_level is not capture_readiness.evidence_level
        or capture_readiness.evidence_level is not evidence_level
        or capture_readiness.source_type is not source_type
        or not capture_run_times_valid
    ):
        provenance_gate_passed = False
        issues.append(
            _gate_issue(
                "capture_assessment_provenance_invalid",
                "Capture assessment run is not clean, completed and evidence-bound",
                error=True,
            )
        )
    variant_reports: list[FallEventVariantEvaluation] = []
    for binding in sorted(bundle.predictions, key=lambda item: item.variant_id):
        prediction_path = _verified_path(
            bundle_root,
            binding.candidate_events,
            kind="candidate events",
        )
        source_run_path = _verified_path(
            bundle_root,
            binding.source_run_manifest,
            kind="candidate source run",
        )
        assets.extend(
            (
                _asset(
                    prediction_path,
                    modality=Modality.VIDEO,
                    source_type=source_type,
                    evidence_level=evidence_level,
                ),
                _asset(
                    source_run_path,
                    modality=Modality.DEVICE_SNAPSHOT,
                    source_type=source_type,
                    evidence_level=evidence_level,
                ),
            )
        )
        prediction = _load_json(
            prediction_path,
            FallCandidatePredictionSet,
            kind="candidate events",
        )
        source_run = _load_json(
            source_run_path,
            RunManifest,
            kind="candidate source run",
        )
        if prediction.variant_id != binding.variant_id:
            raise ValueError("candidate events variant disagrees with bundle")
        if prediction.source_run_id != source_run.run_id:
            raise ValueError("candidate events source run id is inconsistent")
        if prediction.capture_manifest_sha256 != context.manifest_sha256:
            raise ValueError("candidate events refer to another capture manifest")
        if prediction.model_policy_sha256 != expected_variants[binding.variant_id]:
            raise ValueError("candidate events model policy differs from event policy")
        if (
            prediction.fall_feature_policy_sha256
            != policy.expected_fall_feature_policy_sha256
        ):
            raise ValueError("candidate events feature policy differs from event policy")
        if (
            prediction.candidate_generator_policy_sha256
            != candidate_policy_sha256
        ):
            raise ValueError("candidate events generator policy differs from bundle")
        _validate_clip_set(prediction.clips, context, kind="prediction")
        if source_run.stage != policy.source_candidate_stage:
            raise ValueError("candidate source run stage is invalid")
        _validate_run_configuration(
            source_run,
            {
                "variant_id": binding.variant_id,
                "capture_manifest_sha256": context.manifest_sha256,
                "model_policy_sha256": prediction.model_policy_sha256,
                "fall_feature_policy_sha256": (
                    prediction.fall_feature_policy_sha256
                ),
                "candidate_generator_policy_sha256": (
                    candidate_policy_sha256
                ),
                "candidate_events_sha256": sha256_file(prediction_path),
            },
            kind="candidate source",
        )
        source_run_times_valid = (
            source_run.finished_at is not None
            and source_run.started_at.utcoffset() is not None
            and source_run.finished_at.utcoffset() is not None
        )
        source_valid = (
            source_run_times_valid
            and source_run.status is RunStatus.COMPLETED
            and source_run.finished_at is not None
            and not source_run.code_dirty
            and source_run.code_version != "unknown"
            and source_run.evidence_level is evidence_level
            and source_run.started_at >= adjudication.frozen_at
            and prediction.generated_at >= source_run.started_at
            and prediction.generated_at <= source_run.finished_at
        )
        if context.first_inference_at is None:
            source_valid = False
        else:
            source_valid = source_valid and (
                context.first_inference_at >= context.labels_frozen_at
                and source_run.started_at >= context.first_inference_at
            )
        if not source_valid:
            provenance_gate_passed = False
            issues.append(
                _gate_issue(
                    "candidate_source_provenance_invalid",
                    "A candidate source run violates clean held-out provenance",
                    error=True,
                )
            )
        variant_reports.append(
            _variant_evaluation(
                prediction,
                source_run,
                adjudication,
                context,
                policy,
            )
        )

    if not annotations_complete:
        issues.append(
            _gate_issue(
                "annotation_coverage_incomplete",
                "Independent annotation count or action-label coverage is below policy",
                error=True,
            )
        )
    if not agreement_gate_passed:
        issues.append(
            _gate_issue(
                "annotation_agreement_below_policy",
                "Pairwise interval or target-onset agreement is below policy",
                error=True,
            )
        )
    if not adjudication_complete:
        issues.append(
            _gate_issue(
                "adjudication_incomplete",
                "Adjudicated labels do not close all required action coverage",
                error=True,
            )
        )
    if not minimum_data_gate_passed:
        issues.append(
            _gate_issue(
                "minimum_event_data_not_met",
                "Held-out positive or negative event coverage is below policy",
                error=True,
            )
        )
    capture_camera_gate_passed = (
        capture_readiness.camera_ready_for_model_retest
        and all(clip.structurally_usable for clip in capture_readiness.clips)
    )
    if not capture_camera_gate_passed:
        issues.append(
            _gate_issue(
                "capture_camera_gate_closed",
                "The real-device camera retest gate is not open",
            )
        )
    real_evidence = (
        source_type is not SourceType.FIXTURE
        and EVIDENCE_RANK[evidence_level] >= EVIDENCE_RANK[EvidenceLevel.E2]
        and not bundle.fixture
        and not context.synthetic
        and not context.template_only
    )
    core_gates = (
        annotations_complete,
        agreement_gate_passed,
        adjudication_complete,
        minimum_data_gate_passed,
        provenance_gate_passed,
    )
    event_ready = real_evidence and capture_camera_gate_passed and all(core_gates)
    if event_ready:
        decision = "event_metrics_ready_for_review"
        quality_status = QualityStatus.PASS
    elif all(core_gates) and not real_evidence:
        decision = "tooling_only"
        quality_status = QualityStatus.PARTIAL
        issues.append(
            _gate_issue(
                "fixture_or_sub_e2_evidence",
                "Tooling results cannot be promoted to real event performance",
            )
        )
    elif all(core_gates):
        decision = "capture_gate_closed"
        quality_status = QualityStatus.PARTIAL
    else:
        decision = "not_ready"
        quality_status = QualityStatus.FAIL

    exposure_ms = sum(clip.duration_ms for clip in context.clips)
    report = FallEventEvaluationReadinessReport(
        assessor_version=ASSESSOR_VERSION,
        evaluation_ref=f"evaluation_{bundle_sha256[:16]}",
        evidence_level=evidence_level,
        source_type=source_type,
        bundle_sha256=bundle_sha256,
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        capture_ref=context.capture_ref,
        capture_manifest_sha256=context.manifest_sha256,
        capture_readiness_sha256=capture_readiness_sha256,
        candidate_generator_policy_sha256=candidate_policy_sha256,
        template_only=context.template_only,
        synthetic=context.synthetic,
        fixture=bundle.fixture,
        required_variant_ids=sorted(expected_variants),
        clip_count=len(context.clips),
        exposure_ms=exposure_ms,
        annotation_set_count=len(annotations),
        annotation_agreements=agreements,
        ground_truth_event_count=ground_truth_event_count,
        negative_clip_count=negative_clip_count,
        annotations_complete=annotations_complete,
        agreement_gate_passed=agreement_gate_passed,
        adjudication_complete=adjudication_complete,
        minimum_data_gate_passed=minimum_data_gate_passed,
        provenance_gate_passed=provenance_gate_passed,
        capture_camera_gate_passed=capture_camera_gate_passed,
        variants=variant_reports,
        event_metrics_ready_for_review=event_ready,
        decision=decision,
        quality_status=quality_status,
        issues=issues,
        limitations=[
            *bundle.limitations,
            "the_evaluator_scores_external_candidates_and_does_not_define_fall_logic",
            "annotation_and_candidate_timestamps_are_never_copied_to_the_report",
            "fixture_metrics_are_contract_tests_not_model_performance",
            "risk_assessment_and_alert_generation_are_out_of_scope",
        ],
    )
    return FallEventEvaluationAssessment(assets=assets, report=report)
