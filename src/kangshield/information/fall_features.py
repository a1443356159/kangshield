from __future__ import annotations

import bisect
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .artifacts import RunArtifacts
from .contracts import (
    DatasetBenchmarkCase,
    EvidenceLevel,
    FallFeatureBenchmarkReport,
    FallFeatureCaseEvaluation,
    FallFeatureConfig,
    FallFeatureMetrics,
    FallKeypointGate,
    FallMotionFrameValue,
    FeatureEvent,
    Modality,
    ModelBinding,
    PoseBenchmarkVariantReport,
    PoseModelComparisonReport,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    SourceAsset,
    SourceType,
)
from .dataset_benchmark import PHASE_NAMES, load_benchmark_cases
from .privacy import safe_local_uri, sha256_file


FALL_FEATURE_BENCHMARK_VERSION = "fall-feature-benchmark-v0.1.0"


@dataclass(frozen=True)
class _HistorySample:
    timestamp_ms: int
    center_x: float
    center_y: float
    track_id: int
    horizontal: bool


@dataclass(frozen=True)
class _SourcePoseContext:
    report_path: Path
    report: PoseModelComparisonReport
    parent_run_id: str
    parent_run_dir: Path
    runs_dir: Path
    manifest_path: Path
    manifest: RunManifest


def load_fall_feature_config(path: Path) -> FallFeatureConfig:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    return FallFeatureConfig.model_validate(payload)


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _valid_bbox(detection: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(detection, dict):
        return None
    bbox = detection.get("bbox_xyxy")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    values = [_finite_float(value) for value in bbox]
    if any(value is None for value in values):
        return None
    x1, y1, x2, y2 = (float(value) for value in values)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _failed_keypoint_gate(
    config: FallFeatureConfig,
    status: str = "failed_no_detection",
) -> FallKeypointGate:
    return FallKeypointGate(
        expected_layout=config.expected_keypoint_layout,
        expected_count=config.expected_keypoint_count,
        observed_count=0,
        confidence_threshold=config.keypoint_confidence_threshold,
        visible_count=0,
        visible_ratio=None,
        visible_ratio_threshold=config.keypoint_visible_ratio_threshold,
        required_indices=config.required_keypoint_indices,
        required_visible_count=0,
        required_all_visible=False,
        status=status,
        geometry_available=False,
    )


def _keypoint_gate(
    detection: dict[str, Any],
    config: FallFeatureConfig,
) -> FallKeypointGate:
    points = detection.get("keypoints_xyc")
    if not isinstance(points, list):
        return _failed_keypoint_gate(config, "failed_layout")
    observed_count = len(points)
    if observed_count != config.expected_keypoint_count:
        gate = _failed_keypoint_gate(config, "failed_layout")
        gate.observed_count = observed_count
        return gate

    scores: list[float | None] = []
    coordinates: list[tuple[float, float] | None] = []
    for point in points:
        if not isinstance(point, list) or len(point) < 3:
            scores.append(None)
            coordinates.append(None)
            continue
        x = _finite_float(point[0])
        y = _finite_float(point[1])
        score = _finite_float(point[2])
        scores.append(score)
        coordinates.append((x, y) if x is not None and y is not None else None)

    visible = [
        score is not None and score >= config.keypoint_confidence_threshold
        for score in scores
    ]
    visible_count = sum(visible)
    visible_ratio = visible_count / config.expected_keypoint_count
    required_visible_count = sum(
        visible[index] and coordinates[index] is not None
        for index in config.required_keypoint_indices
    )
    required_all_visible = required_visible_count == len(
        config.required_keypoint_indices
    )
    common = {
        "expected_layout": config.expected_keypoint_layout,
        "expected_count": config.expected_keypoint_count,
        "observed_count": observed_count,
        "confidence_threshold": config.keypoint_confidence_threshold,
        "visible_count": visible_count,
        "visible_ratio": round(visible_ratio, 6),
        "visible_ratio_threshold": config.keypoint_visible_ratio_threshold,
        "required_indices": config.required_keypoint_indices,
        "required_visible_count": required_visible_count,
        "required_all_visible": required_all_visible,
    }
    if not required_all_visible:
        return FallKeypointGate(
            **common,
            status="failed_required_points",
            geometry_available=False,
        )
    if visible_ratio < config.keypoint_visible_ratio_threshold:
        return FallKeypointGate(
            **common,
            status="failed_visible_ratio",
            geometry_available=False,
        )

    left_shoulder, right_shoulder, left_hip, right_hip = (
        coordinates[index] for index in config.required_keypoint_indices
    )
    assert left_shoulder is not None
    assert right_shoulder is not None
    assert left_hip is not None
    assert right_hip is not None
    shoulder_midpoint = (
        (left_shoulder[0] + right_shoulder[0]) / 2.0,
        (left_shoulder[1] + right_shoulder[1]) / 2.0,
    )
    hip_midpoint = (
        (left_hip[0] + right_hip[0]) / 2.0,
        (left_hip[1] + right_hip[1]) / 2.0,
    )
    dx = hip_midpoint[0] - shoulder_midpoint[0]
    dy = hip_midpoint[1] - shoulder_midpoint[1]
    if math.hypot(dx, dy) <= 1e-9:
        return FallKeypointGate(
            **common,
            status="failed_degenerate_geometry",
            geometry_available=False,
        )
    angle = math.degrees(math.atan2(abs(dy), abs(dx)))
    return FallKeypointGate(
        **common,
        status="passed",
        geometry_available=True,
        torso_angle_from_horizontal_deg=round(angle, 6),
        torso_horizontal_proxy=(
            angle <= config.torso_horizontal_angle_max_deg
        ),
    )


class FallMotionFeatureExtractor:
    """Stateful, single-primary-box feature extractor; never emits a risk score."""

    def __init__(
        self,
        config: FallFeatureConfig,
        *,
        frame_width: int,
        frame_height: int,
    ) -> None:
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame dimensions must be positive")
        self.config = config
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_diagonal = math.hypot(frame_width, frame_height)
        self._history: deque[_HistorySample] = deque()
        self._active_track_id: int | None = None
        self._last_timestamp_ms: int | None = None
        self._horizontal_started_ms: int | None = None

    def reset(self) -> None:
        self._history.clear()
        self._active_track_id = None
        self._last_timestamp_ms = None
        self._horizontal_started_ms = None

    def _reset_temporal_state(self) -> None:
        self._history.clear()
        self._active_track_id = None
        self._horizontal_started_ms = None

    def process(self, pose_event: FeatureEvent) -> FallMotionFrameValue:
        if pose_event.feature_type != "video.pose_frame":
            raise ValueError("fall features require a video.pose_frame source")
        timestamp_ms = pose_event.time_range.start_ms
        if timestamp_ms is None:
            raise ValueError("pose frame requires a relative start_ms")
        if (
            self._last_timestamp_ms is not None
            and timestamp_ms <= self._last_timestamp_ms
        ):
            raise ValueError("pose frame timestamps must be strictly increasing")

        payload = pose_event.value
        if not isinstance(payload, dict):
            raise ValueError("pose frame value must be an object")
        frame_sequence = payload.get("frame_sequence")
        detections = payload.get("detections")
        if (
            isinstance(frame_sequence, bool)
            or not isinstance(frame_sequence, int)
            or frame_sequence < 0
        ):
            raise ValueError("pose frame_sequence must be a non-negative integer")
        if not isinstance(detections, list):
            raise ValueError("pose detections must be a list")
        declared_person_count = payload.get("person_count")
        if declared_person_count != len(detections):
            raise ValueError("pose person_count does not match detections")

        gap_reset = (
            self._last_timestamp_ms is not None
            and timestamp_ms - self._last_timestamp_ms
            > self.config.max_frame_gap_ms
        )
        self._last_timestamp_ms = timestamp_ms
        reasons: list[str] = []
        if gap_reset:
            self._reset_temporal_state()
            _add_reason(reasons, "frame_gap_history_reset")

        valid: list[
            tuple[int, dict[str, Any], tuple[float, float, float, float], float]
        ] = []
        for index, detection in enumerate(detections):
            bbox = _valid_bbox(detection)
            if bbox is None or not isinstance(detection, dict):
                continue
            x1, y1, x2, y2 = bbox
            valid.append((index, detection, bbox, (x2 - x1) * (y2 - y1)))

        if not valid:
            self._reset_temporal_state()
            _add_reason(
                reasons,
                "no_person_detection" if not detections else "no_valid_bbox",
            )
            return FallMotionFrameValue(
                feature_version=self.config.feature_version,
                frame_sequence=frame_sequence,
                timestamp_ms=timestamp_ms,
                frame_width=self.frame_width,
                frame_height=self.frame_height,
                person_count=len(detections),
                active_path="unavailable",
                fallback_reasons=reasons,
                keypoint_gate=_failed_keypoint_gate(self.config),
            )

        if len(detections) > 1:
            _add_reason(reasons, "multiple_people_largest_bbox_only")
        index, detection, bbox, _ = max(valid, key=lambda item: (item[3], -item[0]))
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        ratio = width / height
        horizontal = ratio >= self.config.bbox_horizontal_ratio_threshold

        track_value = detection.get("track_id")
        track_id = (
            int(track_value)
            if isinstance(track_value, int) and not isinstance(track_value, bool)
            else None
        )
        history_reset = False
        if track_id is None:
            self._reset_temporal_state()
            _add_reason(reasons, "track_id_missing_temporal_features_unavailable")
        elif self._active_track_id is not None and track_id != self._active_track_id:
            self._reset_temporal_state()
            history_reset = True
            _add_reason(reasons, "track_changed_history_reset")

        descent_span: int | None = None
        center_drop: float | None = None
        rapid_descent: bool | None = None
        stationary_span: int | None = None
        max_displacement: float | None = None
        low_motion: bool | None = None
        horizontal_duration: int | None = 0

        if track_id is not None:
            if self._active_track_id is None:
                self._active_track_id = track_id
            sample = _HistorySample(
                timestamp_ms=timestamp_ms,
                center_x=center_x,
                center_y=center_y,
                track_id=track_id,
                horizontal=horizontal,
            )
            self._history.append(sample)
            maximum_window = max(
                self.config.descent_history_window_ms,
                self.config.stationary_window_ms,
            )
            while (
                self._history
                and timestamp_ms - self._history[0].timestamp_ms > maximum_window
            ):
                self._history.popleft()

            descent_candidates = [
                item
                for item in self._history
                if timestamp_ms - item.timestamp_ms
                <= self.config.descent_history_window_ms
            ]
            descent_span = timestamp_ms - descent_candidates[0].timestamp_ms
            if descent_span >= self.config.descent_min_span_ms:
                center_drop = (
                    center_y - descent_candidates[0].center_y
                ) / self.frame_height
                center_drop = round(center_drop, 6)
                rapid_descent = (
                    center_drop
                    >= self.config.rapid_descent_center_y_ratio_threshold
                )
            else:
                _add_reason(reasons, "descent_history_not_ready")

            stationary_candidates = [
                item
                for item in self._history
                if timestamp_ms - item.timestamp_ms
                <= self.config.stationary_window_ms
            ]
            stationary_span = timestamp_ms - stationary_candidates[0].timestamp_ms
            if stationary_span >= self.config.stationary_min_span_ms:
                max_displacement = max(
                    math.hypot(
                        center_x - item.center_x,
                        center_y - item.center_y,
                    )
                    / self.frame_diagonal
                    for item in stationary_candidates
                )
                max_displacement = round(max_displacement, 6)
                low_motion = (
                    max_displacement
                    <= self.config.stationary_center_displacement_diagonal_ratio_threshold
                )
            else:
                _add_reason(reasons, "stationary_history_not_ready")

            if horizontal:
                if self._horizontal_started_ms is None or history_reset:
                    self._horizontal_started_ms = timestamp_ms
                horizontal_duration = timestamp_ms - self._horizontal_started_ms
            else:
                self._horizontal_started_ms = None
                horizontal_duration = 0

        gate = _keypoint_gate(detection, self.config)
        if gate.status == "passed":
            active_path = "box_plus_keypoints"
        else:
            active_path = "box_only"
            _add_reason(reasons, f"keypoint_gate_{gate.status}_use_box_only")

        return FallMotionFrameValue(
            feature_version=self.config.feature_version,
            frame_sequence=frame_sequence,
            timestamp_ms=timestamp_ms,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            person_count=len(detections),
            selected_detection_index=index,
            selected_track_id=track_id,
            active_path=active_path,
            fallback_reasons=reasons,
            bbox_width_height_ratio=round(ratio, 6),
            bbox_center_x_ratio=round(center_x / self.frame_width, 6),
            bbox_center_y_ratio=round(center_y / self.frame_height, 6),
            bbox_bottom_y_ratio=round(y2 / self.frame_height, 6),
            bbox_area_frame_ratio=round(
                width * height / (self.frame_width * self.frame_height), 6
            ),
            bbox_horizontal_proxy=horizontal,
            horizontal_duration_ms=horizontal_duration,
            descent_history_span_ms=descent_span,
            center_drop_frame_height_ratio=center_drop,
            rapid_descent_proxy=rapid_descent,
            stationary_history_span_ms=stationary_span,
            max_center_displacement_diagonal_ratio=max_displacement,
            low_motion_proxy=low_motion,
            keypoint_gate=gate,
        )


def summarize_fall_features(
    frames: Iterable[FallMotionFrameValue],
) -> FallFeatureMetrics:
    values = list(frames)
    box = [value for value in values if value.bbox_width_height_ratio is not None]
    descent = [value for value in box if value.rapid_descent_proxy is not None]
    stationary = [value for value in box if value.low_motion_proxy is not None]
    torso = [
        value
        for value in box
        if value.keypoint_gate.torso_horizontal_proxy is not None
    ]
    reasons = Counter(
        reason for value in values for reason in value.fallback_reasons
    )

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 0.0

    horizontal_count = sum(value.bbox_horizontal_proxy is True for value in box)
    rapid_count = sum(value.rapid_descent_proxy is True for value in descent)
    low_motion_count = sum(value.low_motion_proxy is True for value in stationary)
    gate_count = sum(value.keypoint_gate.status == "passed" for value in box)
    torso_horizontal_count = sum(
        value.keypoint_gate.torso_horizontal_proxy is True for value in torso
    )
    return FallFeatureMetrics(
        sampled_frames=len(values),
        unavailable_frames=sum(value.active_path == "unavailable" for value in values),
        box_available_frames=len(box),
        box_only_frames=sum(value.active_path == "box_only" for value in values),
        box_plus_keypoints_frames=sum(
            value.active_path == "box_plus_keypoints" for value in values
        ),
        bbox_horizontal_frames=horizontal_count,
        bbox_horizontal_rate=rate(horizontal_count, len(box)),
        maximum_horizontal_duration_ms=max(
            (
                value.horizontal_duration_ms
                for value in box
                if value.horizontal_duration_ms is not None
            ),
            default=0,
        ),
        descent_available_frames=len(descent),
        rapid_descent_frames=rapid_count,
        rapid_descent_rate=rate(rapid_count, len(descent)),
        stationary_available_frames=len(stationary),
        low_motion_frames=low_motion_count,
        low_motion_rate=rate(low_motion_count, len(stationary)),
        keypoint_gate_passed_frames=gate_count,
        keypoint_gate_pass_rate=rate(gate_count, len(box)),
        torso_horizontal_available_frames=len(torso),
        torso_horizontal_frames=torso_horizontal_count,
        torso_horizontal_rate=rate(torso_horizontal_count, len(torso)),
        fallback_reason_counts=dict(sorted(reasons.items())),
    )


def _load_source_context(
    report_path: Path,
    *,
    allow_dirty_source: bool,
) -> _SourcePoseContext:
    report_path = Path(report_path).resolve()
    if report_path.name != "pose-model-comparison-report.json":
        raise ValueError("source must be a pose model comparison report")
    if report_path.parent.name != "reports":
        raise ValueError("source pose report must be inside a reports directory")
    parent_run_dir = report_path.parent.parent
    runs_dir = parent_run_dir.parent
    parent_run_id = parent_run_dir.name
    if Path(parent_run_id).name != parent_run_id:
        raise ValueError("source pose run id is invalid")
    manifest_path = parent_run_dir / "manifest.json"
    if not manifest_path.is_file() or not report_path.is_file():
        raise FileNotFoundError("source pose comparison artifacts are incomplete")
    report = PoseModelComparisonReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    manifest = RunManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.run_id != parent_run_id:
        raise ValueError("source pose manifest run id does not match its directory")
    if manifest.stage != "v1-m3-pose-model-comparison":
        raise ValueError("source pose manifest has the wrong stage")
    if manifest.status is not RunStatus.COMPLETED:
        raise ValueError("source pose comparison is not completed")
    if manifest.evidence_level is not EvidenceLevel.E1:
        raise ValueError("source pose comparison must be E1")
    if manifest.code_dirty and not allow_dirty_source:
        raise ValueError("source pose comparison is dirty")
    return _SourcePoseContext(
        report_path=report_path,
        report=report,
        parent_run_id=parent_run_id,
        parent_run_dir=parent_run_dir,
        runs_dir=runs_dir,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _select_variant(
    report: PoseModelComparisonReport,
    variant_id: str,
) -> PoseBenchmarkVariantReport:
    matches = [variant for variant in report.variants if variant.variant_id == variant_id]
    if len(matches) != 1:
        raise ValueError("selected pose variant is not present exactly once")
    return matches[0]


def _pose_binding_digest(
    bindings: list[ModelBinding],
    expected_layout: str,
) -> str:
    matches = [
        binding
        for binding in bindings
        if binding.task in {"human_pose_estimation", "human_pose_tracking"}
    ]
    if len(matches) != 1 or matches[0].model_digest is None:
        raise ValueError("selected variant must have one digest-bound pose model")
    if matches[0].configuration.get("keypoint_layout") != expected_layout:
        raise ValueError("source pose binding keypoint layout does not match config")
    return matches[0].model_digest


def correct_model_bindings(
    bindings: list[ModelBinding],
    *,
    variant_id: str,
    policy_path: Path,
) -> tuple[list[ModelBinding], list[str]]:
    with Path(policy_path).open(encoding="utf-8") as stream:
        policy = json.load(stream)
    models = policy.get("models")
    if not isinstance(models, list):
        raise ValueError("pose model policy contains no model list")
    by_digest: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("pose model policy contains an invalid model entry")
        digest = model.get("onnx_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("pose model policy contains an invalid model digest")
        by_digest[digest] = model

    corrected: list[ModelBinding] = []
    corrections: list[str] = []
    matched_digests: set[str] = set()
    policy_digest = sha256_file(Path(policy_path))
    for binding in bindings:
        model = by_digest.get(binding.model_digest or "")
        if model is None:
            corrected.append(binding.model_copy(deep=True))
            continue
        license_value = model.get("license")
        if not isinstance(license_value, str) or not license_value:
            raise ValueError("pose model policy is missing an artifact license")
        updated = binding.model_copy(deep=True)
        if updated.license != license_value:
            corrections.append(
                f"{updated.model_name}:{updated.license}->{license_value}"
            )
        updated.license = license_value
        updated.configuration.update(
            {
                "implementation_license": model.get("implementation_license"),
                "training_domain": model.get("training_domain"),
                "training_data_terms": model.get("training_data_terms"),
                "model_artifact_distribution_status": model.get(
                    "distribution_status"
                ),
                "license_policy_sha256": policy_digest,
                "license_sources": policy.get("license_sources", []),
            }
        )
        matched_digests.add(binding.model_digest or "")
        corrected.append(updated)

    if variant_id == "rtmpose-m-humanart":
        required = {
            str(model["onnx_sha256"])
            for model in models
            if model.get("model_id")
            in {"yolox-m-humanart", "rtmpose-m-humanart"}
        }
        if matched_digests != required:
            raise ValueError("source HumanArt model digests do not match policy")
        if any(
            binding.model_digest in required
            and binding.license != "model-artifact-license-review-required"
            for binding in corrected
        ):
            raise ValueError("HumanArt artifact license must remain fail closed")
    return corrected, corrections


def validate_torchvision_model_bindings(
    bindings: list[ModelBinding],
    *,
    policy_path: Path,
) -> list[ModelBinding]:
    from .torchvision_pose_backend import (
        TORCHVISION_KEYPOINT_RCNN_SHA256,
        TORCHVISION_MODEL_ARTIFACT_LICENSE,
        load_torchvision_pose_policy,
    )

    load_torchvision_pose_policy(policy_path)
    policy_digest = sha256_file(Path(policy_path))
    corrected = [binding.model_copy(deep=True) for binding in bindings]
    matches = [
        binding
        for binding in corrected
        if binding.task in {"human_pose_estimation", "human_pose_tracking"}
    ]
    if len(matches) != 1:
        raise ValueError("Keypoint R-CNN source must expose exactly one pose binding")
    pose = matches[0]
    if pose.model_digest != TORCHVISION_KEYPOINT_RCNN_SHA256:
        raise ValueError("Keypoint R-CNN source weight digest is not frozen")
    if pose.license != TORCHVISION_MODEL_ARTIFACT_LICENSE:
        raise ValueError("Keypoint R-CNN source artifact license must remain fail closed")
    if pose.configuration.get("license_policy_sha256") != policy_digest:
        raise ValueError("Keypoint R-CNN source policy binding digest is not frozen")
    return corrected


def _source_asset(
    path: Path,
    *,
    kind: str,
    modality: Modality,
    privacy_level: PrivacyLevel,
) -> SourceAsset:
    digest = sha256_file(Path(path))
    return SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=modality,
        source_type=SourceType.LOCAL_FILE,
        evidence_level=EvidenceLevel.E1,
        uri=safe_local_uri(Path(path), digest),
        sha256=digest,
        byte_size=Path(path).stat().st_size,
        privacy_level=privacy_level,
        metadata={
            "kind": kind,
            "filename_suffix": Path(path).suffix.lower(),
            "contains_raw_media": False,
            "source_path_persisted": False,
        },
    )


def _read_annotation(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        annotation = json.load(stream)
    frames = annotation.get("frames")
    if annotation.get("schema_version") != "1.0" or not isinstance(frames, list):
        raise ValueError("invalid posture annotation sidecar")
    if not frames:
        raise ValueError("posture annotation sidecar contains no frames")
    if not isinstance(annotation.get("width"), int) or annotation["width"] <= 0:
        raise ValueError("posture annotation width is invalid")
    if not isinstance(annotation.get("height"), int) or annotation["height"] <= 0:
        raise ValueError("posture annotation height is invalid")
    return annotation


def _nearest_annotation(
    timestamps: list[int],
    frames: list[dict[str, Any]],
    timestamp_ms: int,
) -> tuple[dict[str, Any], int]:
    insertion = bisect.bisect_left(timestamps, timestamp_ms)
    candidates = [
        index
        for index in (insertion - 1, insertion)
        if 0 <= index < len(timestamps)
    ]
    if not candidates:
        raise ValueError("posture annotation contains no timestamp candidate")
    index = min(candidates, key=lambda item: abs(timestamps[item] - timestamp_ms))
    return frames[index], abs(timestamps[index] - timestamp_ms)


def _read_pose_events(path: Path) -> list[FeatureEvent]:
    events: list[FeatureEvent] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            event = FeatureEvent.model_validate_json(line)
            if event.feature_type == "video.pose_frame":
                events.append(event)
    if not events:
        raise ValueError("source pose feature file contains no pose frames")
    timestamps = [event.time_range.start_ms for event in events]
    if any(value is None for value in timestamps):
        raise ValueError("source pose frame is missing a relative timestamp")
    if any(
        current <= previous
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise ValueError("source pose frame timestamps are not strictly increasing")
    return events


def _safe_child_dir(runs_dir: Path, run_id: str) -> Path:
    if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
        raise ValueError("source child run id is invalid")
    root = Path(runs_dir).resolve()
    child = (root / run_id).resolve()
    if child.parent != root:
        raise ValueError("source child run escapes the runs directory")
    return child


def _safe_benchmark_relative_path(manifest_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError("benchmark input path must be relative")
    root = Path(manifest_path).parent.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("benchmark input escapes the benchmark directory")
    return resolved


def _derived_event(
    *,
    run_id: str,
    case_index: int,
    source: FeatureEvent,
    value: FallMotionFrameValue,
) -> FeatureEvent:
    return FeatureEvent(
        feature_id=(
            f"feature_{run_id}_fall_{case_index:02d}_{value.frame_sequence:06d}"
        ),
        observation_id=source.observation_id,
        feature_type="video.fall_motion_frame",
        time_range=source.time_range,
        value=value.model_dump(mode="json"),
        confidence=None,
        quality=None,
        extractor_name="kangshield-fall-motion-features",
        extractor_version=value.feature_version,
        model_digest=None,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        source_feature_refs=[source.feature_id],
        limitations=[
            "not_a_risk_assessment",
            "largest_bbox_is_not_person_identity",
            "uncalibrated_image_coordinates",
            "public_dataset_e1_only",
        ],
    )


def run_fall_feature_benchmark(
    *,
    benchmark_cases_path: Path,
    pose_comparison_report_path: Path,
    runs_dir: Path,
    variant_id: str,
    config_path: Path,
    model_binding_policy_path: Path,
    torchvision_policy_path: Path = Path(
        "configs/v1-m3-torchvision-pose-model.json"
    ),
    allow_dirty_source: bool = False,
) -> tuple[RunArtifacts, FallFeatureBenchmarkReport]:
    benchmark_cases_path = Path(benchmark_cases_path).resolve()
    config_path = Path(config_path).resolve()
    model_binding_policy_path = Path(model_binding_policy_path).resolve()
    torchvision_policy_path = Path(torchvision_policy_path).resolve()
    config = load_fall_feature_config(config_path)
    suite, cases = load_benchmark_cases(benchmark_cases_path)
    context = _load_source_context(
        pose_comparison_report_path,
        allow_dirty_source=allow_dirty_source,
    )
    benchmark_digest = sha256_file(benchmark_cases_path)
    if context.report.benchmark_id != suite["benchmark_id"]:
        raise ValueError("source pose benchmark id does not match the fixed suite")
    if context.report.benchmark_cases_sha256 != benchmark_digest:
        raise ValueError("source pose benchmark digest does not match the fixed suite")
    if context.report.case_count != len(cases):
        raise ValueError("source pose benchmark case count does not match the suite")
    variant = _select_variant(context.report, variant_id)
    expected_case_ids = [case.case_id for case in cases]
    source_case_ids = [case.case_id for case in variant.cases]
    if source_case_ids != expected_case_ids:
        raise ValueError("source pose cases do not match the benchmark case order")
    if variant_id == "torchvision-keypointrcnn":
        selected_policy_path = torchvision_policy_path
        bindings = validate_torchvision_model_bindings(
            variant.model_bindings,
            policy_path=selected_policy_path,
        )
        corrections: list[str] = []
    else:
        selected_policy_path = model_binding_policy_path
        bindings, corrections = correct_model_bindings(
            variant.model_bindings,
            variant_id=variant_id,
            policy_path=selected_policy_path,
        )
    expected_pose_digest = _pose_binding_digest(
        bindings,
        config.expected_keypoint_layout,
    )

    report_digest = sha256_file(context.report_path)
    source_manifest_digest = sha256_file(context.manifest_path)
    config_digest = sha256_file(config_path)
    policy_digest = sha256_file(selected_policy_path)
    configuration = {
        "command": "benchmark-fall-features",
        "benchmark_id": suite["benchmark_id"],
        "benchmark_cases_sha256": benchmark_digest,
        "source_pose_comparison_run_id": context.parent_run_id,
        "source_pose_comparison_sha256": report_digest,
        "variant_id": variant_id,
        "feature_version": config.feature_version,
        "configuration_sha256": config_digest,
        "model_binding_policy_sha256": policy_digest,
        "allow_dirty_source": allow_dirty_source,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }

    case_values: dict[str, list[FallMotionFrameValue]] = {}
    case_phases: dict[str, dict[str, list[FallMotionFrameValue]]] = {}
    evaluations: list[FallFeatureCaseEvaluation] = []
    recorded_assets: set[str] = set()

    def record_once(run: RunArtifacts, asset: SourceAsset) -> None:
        if asset.asset_id in recorded_assets:
            return
        recorded_assets.add(asset.asset_id)
        run.record_asset(asset)

    with RunArtifacts(
        runs_dir,
        stage="v1-g4-fall-feature-benchmark",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    ) as run:
        with run.step("record-fall-feature-inputs") as step:
            for path, kind, modality, privacy in (
                (
                    benchmark_cases_path,
                    "benchmark_cases",
                    Modality.VIDEO,
                    PrivacyLevel.AGGREGATE,
                ),
                (
                    context.report_path,
                    "pose_comparison_report",
                    Modality.VIDEO,
                    PrivacyLevel.AGGREGATE,
                ),
                (
                    context.manifest_path,
                    "pose_comparison_manifest",
                    Modality.VIDEO,
                    PrivacyLevel.AGGREGATE,
                ),
                (
                    config_path,
                    "fall_feature_config",
                    Modality.UNKNOWN,
                    PrivacyLevel.AGGREGATE,
                ),
                (
                    selected_policy_path,
                    "pose_model_binding_policy",
                    Modality.UNKNOWN,
                    PrivacyLevel.AGGREGATE,
                ),
            ):
                record_once(
                    run,
                    _source_asset(
                        path,
                        kind=kind,
                        modality=modality,
                        privacy_level=privacy,
                    ),
                )
            step.outputs.append("source_assets.jsonl")

        for case_index, (case, source_case) in enumerate(zip(cases, variant.cases)):
            with run.step(f"derive-fall-features:{case.case_id}") as step:
                child_dir = _safe_child_dir(context.runs_dir, source_case.run_id)
                child_manifest_path = child_dir / "manifest.json"
                feature_path = child_dir / "features.jsonl"
                annotation_path = _safe_benchmark_relative_path(
                    benchmark_cases_path,
                    case.annotation_path,
                )
                if not (
                    child_manifest_path.is_file()
                    and feature_path.is_file()
                    and annotation_path.is_file()
                ):
                    raise FileNotFoundError("source pose case artifacts are incomplete")
                child_manifest = RunManifest.model_validate_json(
                    child_manifest_path.read_text(encoding="utf-8")
                )
                if child_manifest.run_id != source_case.run_id:
                    raise ValueError("source pose child manifest run id mismatch")
                if child_manifest.stage != "v1-m3-pose-model-case":
                    raise ValueError("source pose child manifest has the wrong stage")
                if child_manifest.status is not RunStatus.COMPLETED:
                    raise ValueError("source pose child run is not completed")
                if child_manifest.evidence_level is not EvidenceLevel.E1:
                    raise ValueError("source pose child run must be E1")
                if child_manifest.code_dirty and not allow_dirty_source:
                    raise ValueError("source pose child run is dirty")
                if child_manifest.code_version != context.manifest.code_version:
                    raise ValueError("source pose child code version mismatch")
                if child_manifest.configuration.get("case_id") != case.case_id:
                    raise ValueError("source pose child case id mismatch")
                if child_manifest.configuration.get("variant_id") != variant_id:
                    raise ValueError("source pose child variant mismatch")

                for path, kind, privacy in (
                    (
                        child_manifest_path,
                        "pose_case_manifest",
                        PrivacyLevel.AGGREGATE,
                    ),
                    (
                        feature_path,
                        "pose_case_features",
                        PrivacyLevel.DERIVED_SENSITIVE,
                    ),
                    (
                        annotation_path,
                        "posture_annotation",
                        PrivacyLevel.AGGREGATE,
                    ),
                ):
                    record_once(
                        run,
                        _source_asset(
                            path,
                            kind=kind,
                            modality=Modality.VIDEO,
                            privacy_level=privacy,
                        ),
                    )

                annotation = _read_annotation(annotation_path)
                if annotation.get("sequence") not in {None, case.video_sequence}:
                    raise ValueError("posture annotation sequence does not match case")
                if annotation.get("video_class") not in {None, case.video_class}:
                    raise ValueError("posture annotation class does not match case")
                frames = sorted(
                    annotation["frames"],
                    key=lambda item: int(item["replay_timestamp_ms"]),
                )
                annotation_timestamps = [
                    int(item["replay_timestamp_ms"]) for item in frames
                ]
                source_events = _read_pose_events(feature_path)
                if len(source_events) != source_case.sampled_frames:
                    raise ValueError("source pose feature count does not match report")
                if any(
                    event.model_digest != expected_pose_digest
                    for event in source_events
                ):
                    raise ValueError("source pose feature model digest mismatch")
                extractor = FallMotionFeatureExtractor(
                    config,
                    frame_width=int(annotation["width"]),
                    frame_height=int(annotation["height"]),
                )
                values: list[FallMotionFrameValue] = []
                phases: dict[str, list[FallMotionFrameValue]] = {
                    phase: [] for phase in PHASE_NAMES.values()
                }
                annotation_errors: list[int] = []
                for source_event in source_events:
                    value = extractor.process(source_event)
                    annotation_frame, error = _nearest_annotation(
                        annotation_timestamps,
                        frames,
                        value.timestamp_ms,
                    )
                    if error > config.maximum_annotation_match_error_ms:
                        raise ValueError("pose frame exceeds annotation match tolerance")
                    phase = PHASE_NAMES.get(annotation_frame.get("posture_label"))
                    if phase is None:
                        raise ValueError("posture annotation contains an unknown phase")
                    values.append(value)
                    phases[phase].append(value)
                    annotation_errors.append(error)
                    run.record_feature(
                        _derived_event(
                            run_id=run.run_id,
                            case_index=case_index,
                            source=source_event,
                            value=value,
                        )
                    )

                evaluation = FallFeatureCaseEvaluation(
                    case_id=case.case_id,
                    variant_id=variant_id,
                    video_sequence=case.video_sequence,
                    video_class=case.video_class,
                    source_pose_run_id=source_case.run_id,
                    source_pose_code_version=child_manifest.code_version,
                    source_pose_code_dirty=child_manifest.code_dirty,
                    source_pose_manifest_sha256=sha256_file(child_manifest_path),
                    source_features_sha256=sha256_file(feature_path),
                    annotation_sha256=sha256_file(annotation_path),
                    frame_width=int(annotation["width"]),
                    frame_height=int(annotation["height"]),
                    sampled_frames=len(values),
                    maximum_annotation_match_error_ms=max(
                        annotation_errors, default=0
                    ),
                    overall_metrics=summarize_fall_features(values),
                    phase_metrics={
                        phase: summarize_fall_features(items)
                        for phase, items in phases.items()
                    },
                    limitations=[
                        *case.limitations,
                        "urfd_posture_phases_are_not_fall_classifier_ground_truth",
                        "largest_bbox_selection_is_single_primary_person_only",
                        "thresholds_are_e1_engineering_proxies_not_clinical_cutoffs",
                    ],
                )
                report_path = run.write_report(
                    f"fall-feature-case-{case_index:02d}.json",
                    evaluation,
                )
                step.outputs.extend(["features.jsonl", run.relative(report_path)])
                evaluations.append(evaluation)
                case_values[case.case_id] = values
                case_phases[case.case_id] = phases

        by_class: dict[str, list[FallMotionFrameValue]] = defaultdict(list)
        by_phase: dict[str, list[FallMotionFrameValue]] = {
            phase: [] for phase in PHASE_NAMES.values()
        }
        for case in cases:
            by_class[case.video_class].extend(case_values[case.case_id])
            for phase in PHASE_NAMES.values():
                by_phase[phase].extend(case_phases[case.case_id][phase])

        report = FallFeatureBenchmarkReport(
            benchmark_id=suite["benchmark_id"],
            benchmark_version=FALL_FEATURE_BENCHMARK_VERSION,
            feature_version=config.feature_version,
            evidence_level=EvidenceLevel.E1,
            benchmark_cases_sha256=benchmark_digest,
            configuration_sha256=config_digest,
            source_pose_comparison_run_id=context.parent_run_id,
            source_pose_comparison_sha256=report_digest,
            source_pose_manifest_sha256=source_manifest_digest,
            source_pose_code_version=context.manifest.code_version,
            source_pose_code_dirty=context.manifest.code_dirty,
            model_binding_policy_sha256=policy_digest,
            source_binding_license_corrections=corrections,
            variant_id=variant_id,
            model_bindings=bindings,
            case_count=len(evaluations),
            cases=evaluations,
            by_video_class={
                name: summarize_fall_features(values)
                for name, values in sorted(by_class.items())
            },
            by_posture_phase={
                phase: summarize_fall_features(values)
                for phase, values in by_phase.items()
            },
            limitations=[
                *suite.get("limitations", []),
                "derived_features_do_not_emit_risk_assessment_or_alert",
                "posture_phase_labels_do_not_support_precision_recall_or_f1_claims",
                "largest_bbox_selection_is_not_multi_person_identity_tracking",
                "temporal_features_reset_on_missing_or_changed_track_ids",
                "thresholds_are_frozen_e1_proxies_and_not_target_device_validated",
                *(
                    [
                        "humanart_model_artifact_distribution_remains_blocked_pending_review"
                    ]
                    if variant_id == "rtmpose-m-humanart"
                    else []
                ),
                *(
                    [
                        "torchvision_weight_distribution_remains_blocked_pending_review"
                    ]
                    if variant_id == "torchvision-keypointrcnn"
                    else []
                ),
            ],
        )
        with run.step("write-fall-feature-benchmark-report") as step:
            report_path = run.write_report(
                "fall-feature-benchmark-report.json",
                report,
            )
            step.outputs.append(run.relative(report_path))
    return run, report
