from __future__ import annotations

import gc
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Callable

from pydantic import BaseModel, ValidationError

from .artifacts import RunArtifacts
from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    FallFeatureCaptureClipReport,
    FallFeatureCaptureReport,
    FallFeatureCaptureSet,
    FallFeatureClipStream,
    FallMotionFrameValue,
    FeatureEvent,
    M2cCaptureReadinessReport,
    Modality,
    ModelBinding,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    SourceAsset,
    SourceType,
    TimeRange,
    ensure_source_evidence_compatible,
    utc_now,
)
from .fall_adl_benchmark import YOLO26N_POSE_SHA256
from .fall_features import (
    FallMotionFeatureExtractor,
    correct_model_bindings,
    load_fall_feature_config,
    summarize_fall_features,
    validate_torchvision_model_bindings,
)
from .m2c_capture import M2cInferenceContext, load_m2c_inference_context
from .pose_backend import PoseBackend, PoseDetection
from .privacy import safe_local_uri, sha256_file
from .streaming import OpenCVVideoReplay


FALL_FEATURE_CAPTURE_STAGE = "v1-g4-fall-feature-capture"
FALL_FEATURE_CAPTURE_PRODUCER_VERSION = "fall-feature-capture-v0.1.0"


@dataclass(frozen=True)
class _ReadinessSource:
    report: M2cCaptureReadinessReport
    report_path: Path
    report_sha256: str
    run: RunManifest
    run_path: Path
    run_sha256: str


@dataclass(frozen=True)
class _ClipRuntime:
    stream: FallFeatureClipStream
    report: FallFeatureCaptureClipReport


def _load_json(path: Path, model: type[BaseModel], *, kind: str) -> BaseModel:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{kind} could not be read as JSON") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"{kind} schema validation failed") from error


def _load_readiness_source(
    *,
    context: M2cInferenceContext,
    readiness_report_path: Path,
    readiness_run_manifest_path: Path,
    evidence_level: EvidenceLevel,
    source_type: SourceType,
    allow_dirty_readiness: bool,
) -> _ReadinessSource:
    report_path = Path(readiness_report_path).resolve()
    run_path = Path(readiness_run_manifest_path).resolve()
    if not report_path.is_file():
        raise FileNotFoundError("capture readiness report not found")
    if not run_path.is_file():
        raise FileNotFoundError("capture assessment run manifest not found")
    report = _load_json(
        report_path,
        M2cCaptureReadinessReport,
        kind="capture readiness report",
    )
    run = _load_json(run_path, RunManifest, kind="capture assessment run")
    assert isinstance(report, M2cCaptureReadinessReport)
    assert isinstance(run, RunManifest)
    report_sha256 = sha256_file(report_path)
    run_sha256 = sha256_file(run_path)
    if report.manifest_sha256 != context.manifest_sha256:
        raise ValueError("capture readiness report refers to another manifest")
    if report.capture_ref != context.capture_ref:
        raise ValueError("capture readiness report capture ref disagrees")
    if report.template_only != context.template_only:
        raise ValueError("capture readiness template marker disagrees")
    if report.synthetic != context.synthetic:
        raise ValueError("capture readiness synthetic marker disagrees")
    if report.evidence_level is not evidence_level:
        raise ValueError("capture readiness evidence level disagrees")
    if report.source_type is not source_type:
        raise ValueError("capture readiness source type disagrees")
    expected_clips = [(clip.clip_ref, clip.scenario_id) for clip in context.clips]
    observed_clips = [(clip.clip_ref, clip.scenario_id) for clip in report.clips]
    if observed_clips != expected_clips:
        raise ValueError("capture readiness clip index differs from the manifest")
    if any(not clip.structurally_usable for clip in report.clips):
        raise ValueError("fall-feature capture requires every clip to be structurally usable")
    if any(issue.severity.value == "error" for issue in report.issues):
        raise ValueError("capture readiness report contains an error issue")
    if source_type is not SourceType.FIXTURE and not report.camera_ready_for_model_retest:
        raise ValueError("real capture camera gate is not ready for model replay")

    if run.stage != "v1-m2c-capture-readiness":
        raise ValueError("capture assessment run stage is invalid")
    if run.status is not RunStatus.COMPLETED or run.finished_at is None:
        raise ValueError("capture assessment run is not completed")
    if run.code_version == "unknown":
        raise ValueError("capture assessment code version is unknown")
    if run.code_dirty and not allow_dirty_readiness:
        raise ValueError("capture assessment run is dirty")
    if run.evidence_level is not evidence_level:
        raise ValueError("capture assessment run evidence level disagrees")
    if any(issue.severity.value == "error" for issue in run.issues):
        raise ValueError("capture assessment run contains an error issue")
    if run.started_at.utcoffset() is None or run.finished_at.utcoffset() is None:
        raise ValueError("capture assessment timestamps require timezones")
    if run.started_at < context.labels_frozen_at:
        raise ValueError("capture assessment precedes frozen labels")
    expected_configuration = {
        "capture_manifest_sha256": context.manifest_sha256,
        "capture_readiness_report_sha256": report_sha256,
    }
    if any(run.configuration.get(key) != value for key, value in expected_configuration.items()):
        raise ValueError("capture assessment run configuration disagrees")
    return _ReadinessSource(
        report=report,
        report_path=report_path,
        report_sha256=report_sha256,
        run=run,
        run_path=run_path,
        run_sha256=run_sha256,
    )


def _source_asset(
    path: Path,
    *,
    kind: str,
    modality: Modality,
    source_type: SourceType,
    evidence_level: EvidenceLevel,
    privacy_level: PrivacyLevel,
    contains_raw_media: bool = False,
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
        privacy_level=privacy_level,
        metadata={
            "kind": kind,
            "filename_suffix": path.suffix.lower(),
            "contains_raw_media": contains_raw_media,
            "source_path_persisted": False,
        },
    )


def _pose_binding(bindings: list[ModelBinding]) -> ModelBinding:
    matches = [
        binding
        for binding in bindings
        if binding.task in {"human_pose_estimation", "human_pose_tracking"}
    ]
    if len(matches) != 1 or matches[0].model_digest is None:
        raise ValueError("capture backend must expose one digest-bound pose model")
    pose = matches[0]
    if pose.configuration.get("keypoint_layout") != "COCO-17":
        raise ValueError("capture backend must expose COCO-17 keypoints")
    inline_tracking = pose.configuration.get("tracking") is True
    explicit_trackers = [
        binding
        for binding in bindings
        if binding.task == "short_term_pose_tracking"
        and binding.configuration.get("enabled") is True
    ]
    if not inline_tracking and len(explicit_trackers) != 1:
        raise ValueError("capture backend must enable tracking")
    return pose


def _validated_bindings(
    *,
    variant_id: str,
    backend: PoseBackend,
    model_policy_path: Path,
) -> tuple[list[ModelBinding], ModelBinding, list[str]]:
    if variant_id == "torchvision-keypointrcnn":
        bindings = validate_torchvision_model_bindings(
            backend.bindings,
            policy_path=model_policy_path,
        )
        corrections: list[str] = []
    else:
        bindings, corrections = correct_model_bindings(
            backend.bindings,
            variant_id=variant_id,
            policy_path=model_policy_path,
        )
    pose = _pose_binding(bindings)
    if variant_id == "yolo26n-pose" and pose.model_digest != YOLO26N_POSE_SHA256:
        raise ValueError("YOLO26n-pose weight digest is not the frozen V1 baseline")
    return bindings, pose, corrections


def _visible_ratio(detections: list[PoseDetection], threshold: float = 0.5) -> float | None:
    values = [
        float(point[2])
        for detection in detections
        for point in detection.keypoints_xyc
        if len(point) >= 3
    ]
    if not values:
        return None
    return sum(value >= threshold for value in values) / len(values)


def _pose_event(
    *,
    run_id: str,
    clip_index: int,
    observation_id: str,
    sequence: int,
    timestamp_ms: int,
    end_ms: int,
    detections: list[PoseDetection],
    binding: ModelBinding,
) -> FeatureEvent:
    confidences = [
        detection.confidence
        for detection in detections
        if detection.confidence is not None
    ]
    quality = _visible_ratio(detections)
    return FeatureEvent(
        feature_id=(
            f"feature_{run_id}_pose_{clip_index:03d}_{sequence:06d}"
        ),
        observation_id=observation_id,
        feature_type="video.pose_frame",
        time_range=TimeRange(start_ms=timestamp_ms, end_ms=end_ms),
        value={
            "frame_sequence": sequence,
            "person_count": len(detections),
            "detections": [
                {
                    "bbox_xyxy": detection.bbox_xyxy,
                    "keypoints_xyc": detection.keypoints_xyc,
                    "confidence": detection.confidence,
                    "track_id": detection.track_id,
                }
                for detection in detections
            ],
        },
        confidence=round(mean(confidences), 6) if confidences else None,
        quality=round(quality, 6) if quality is not None else None,
        extractor_name=binding.backend,
        extractor_version=binding.model_version or "unknown",
        model_digest=binding.model_digest,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        limitations=[
            "uncalibrated_image_coordinates",
            "coco_17_keypoints",
            "capture_bound_held_out_replay",
        ],
    )


def _fall_event(
    *,
    run_id: str,
    clip_index: int,
    source: FeatureEvent,
    value: FallMotionFrameValue,
) -> FeatureEvent:
    return FeatureEvent(
        feature_id=(
            f"feature_{run_id}_fall_{clip_index:03d}_{value.frame_sequence:06d}"
        ),
        observation_id=source.observation_id,
        feature_type="video.fall_motion_frame",
        time_range=source.time_range,
        value=value.model_dump(mode="json"),
        extractor_name="kangshield-fall-motion-features",
        extractor_version=value.feature_version,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        source_feature_refs=[source.feature_id],
        limitations=[
            "not_a_risk_assessment",
            "largest_bbox_is_not_person_identity",
            "capture_bound_held_out_replay",
        ],
    )


def _runtime_environment() -> dict[str, object]:
    result: dict[str, object] = {
        "python": platform.python_version(),
        "slurm_job_id_present": bool(os.environ.get("SLURM_JOB_ID")),
    }
    try:
        import torch
    except ImportError:
        result["torch"] = "unavailable"
        return result
    result["torch"] = torch.__version__
    result["cuda_available"] = torch.cuda.is_available()
    if torch.cuda.is_available():
        result["cuda_device"] = torch.cuda.get_device_name(0)
        result["torch_cuda_peak_memory_allocated_mb"] = round(
            torch.cuda.max_memory_allocated(0) / 1024**2,
            3,
        )
    return result


def _release_backend() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _run_clip(
    *,
    context: M2cInferenceContext,
    clip_index: int,
    backend: PoseBackend,
    pose_binding: ModelBinding,
    config_path: Path,
    run: RunArtifacts,
    sample_fps: float,
) -> _ClipRuntime:
    clip = context.clips[clip_index]
    config = load_fall_feature_config(config_path)
    reset = getattr(backend, "reset", None)
    if not callable(reset):
        raise ValueError("capture backend must expose reset between clips")
    reset()
    sample_period_ms = max(1, round(1000.0 / sample_fps))
    observation_id = f"observation_{run.run_id}_{clip_index:03d}"
    relative_path = f"artifacts/fall-motion-{clip_index:03d}.jsonl"
    replay = OpenCVVideoReplay(
        clip.media_path,
        sample_fps=sample_fps,
        max_duration_s=clip.duration_ms / 1000.0,
    )
    extractor: FallMotionFeatureExtractor | None = None
    values: list[FallMotionFrameValue] = []
    inference_latencies: list[float] = []
    feature_latencies: list[float] = []
    frames_with_people = 0
    tracked_frames = 0
    track_ids: set[int] = set()
    stream_path: Path | None = None
    replay_started = perf_counter()
    with run.step(f"capture-fall-features:{clip_index:03d}") as step:
        for sequence, packet in enumerate(replay):
            if packet.timestamp_ms >= clip.duration_ms:
                raise ValueError("sampled frame timestamp exceeds capture duration")
            height, width = packet.frame.shape[:2]
            if extractor is None:
                extractor = FallMotionFeatureExtractor(
                    config,
                    frame_width=int(width),
                    frame_height=int(height),
                )
            elif (extractor.frame_width, extractor.frame_height) != (
                int(width),
                int(height),
            ):
                raise ValueError("capture frame dimensions changed within a clip")
            inference_started = perf_counter()
            detections = backend.infer(packet.frame)
            inference_latencies.append((perf_counter() - inference_started) * 1000.0)
            end_ms = min(clip.duration_ms, packet.timestamp_ms + sample_period_ms)
            if end_ms <= packet.timestamp_ms:
                raise ValueError("capture frame window has no duration")
            pose_event = _pose_event(
                run_id=run.run_id,
                clip_index=clip_index,
                observation_id=observation_id,
                sequence=sequence,
                timestamp_ms=packet.timestamp_ms,
                end_ms=end_ms,
                detections=detections,
                binding=pose_binding,
            )
            feature_started = perf_counter()
            value = extractor.process(pose_event)
            feature_latencies.append((perf_counter() - feature_started) * 1000.0)
            fall_event = _fall_event(
                run_id=run.run_id,
                clip_index=clip_index,
                source=pose_event,
                value=value,
            )
            run.record_feature(pose_event)
            run.record_feature(fall_event)
            stream_path = run.record_feature_artifact(relative_path, fall_event)
            values.append(value)
            if detections:
                frames_with_people += 1
            ids = {
                detection.track_id
                for detection in detections
                if detection.track_id is not None
            }
            if ids:
                tracked_frames += 1
                track_ids.update(int(value) for value in ids)
        step.outputs.extend(("features.jsonl", relative_path))
    replay_wall_ms = (perf_counter() - replay_started) * 1000.0
    if extractor is None or stream_path is None or not values:
        raise ValueError("capture clip produced no sampled frames")
    coverage_end_ms = values[-1].timestamp_ms + sample_period_ms
    if clip.duration_ms - coverage_end_ms > sample_period_ms:
        raise ValueError("capture replay ended before the declared clip duration")
    metrics = summarize_fall_features(values)
    report = FallFeatureCaptureClipReport(
        clip_ref=clip.clip_ref,
        scenario_id=clip.scenario_id,
        duration_ms=clip.duration_ms,
        sampled_frames=len(values),
        frames_with_people=frames_with_people,
        tracked_frames=tracked_frames,
        unique_track_count=len(track_ids),
        fall_feature_metrics=metrics,
        timing_ms={
            "replay_wall": round(replay_wall_ms, 3),
            "pose_inference_total": round(sum(inference_latencies), 3),
            "pose_inference_mean": round(mean(inference_latencies), 3),
            "fall_feature_total": round(sum(feature_latencies), 3),
        },
        realtime_factors={
            "pose_inference": round(
                sum(inference_latencies) / clip.duration_ms,
                6,
            ),
            "replay_pipeline": round(replay_wall_ms / clip.duration_ms, 6),
        },
        limitations=[
            "largest_bbox_selection_is_single_primary_person_only",
            "feature_thresholds_are_not_target_device_validated",
        ],
    )
    stream = FallFeatureClipStream(
        scenario_id=clip.scenario_id,
        duration_ms=clip.duration_ms,
        observation_id=observation_id,
        relative_path=relative_path,
        sha256=sha256_file(stream_path),
        byte_size=stream_path.stat().st_size,
        frame_count=len(values),
    )
    return _ClipRuntime(stream=stream, report=report)


def run_fall_feature_capture(
    *,
    capture_manifest_path: Path,
    readiness_report_path: Path,
    readiness_run_manifest_path: Path,
    variant_id: str,
    backend_factory: Callable[[Path], PoseBackend],
    config_path: Path,
    runs_dir: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
    sample_fps: float = 5.0,
    allow_dirty_readiness: bool = False,
) -> tuple[RunArtifacts, FallFeatureCaptureSet, FallFeatureCaptureReport]:
    """Run one frozen pose variant and G4 extractor over every capture clip."""

    ensure_source_evidence_compatible(source_type, evidence_level)
    if EVIDENCE_RANK[evidence_level] > EVIDENCE_RANK[EvidenceLevel.E2]:
        raise ValueError("capture feature replay can provide at most E2 evidence")
    if sample_fps <= 0:
        raise ValueError("capture feature sample_fps must be positive")
    capture_manifest_path = Path(capture_manifest_path).resolve()
    config_path = Path(config_path).resolve()
    if not config_path.is_file():
        raise FileNotFoundError("fall feature policy not found")
    context = load_m2c_inference_context(
        capture_manifest_path,
        variant_id=variant_id,
    )
    if context.template_only:
        raise ValueError("template capture cannot be used for feature replay")
    fixture = source_type is SourceType.FIXTURE
    if fixture != context.synthetic:
        raise ValueError("capture synthetic marker disagrees with source type")
    if fixture and evidence_level is not EvidenceLevel.E1:
        raise ValueError("fixture feature capture must remain E1")
    readiness = _load_readiness_source(
        context=context,
        readiness_report_path=readiness_report_path,
        readiness_run_manifest_path=readiness_run_manifest_path,
        evidence_level=evidence_level,
        source_type=source_type,
        allow_dirty_readiness=allow_dirty_readiness,
    )
    feature_config = load_fall_feature_config(config_path)
    config_sha256 = sha256_file(config_path)
    configuration = {
        "command": "capture-fall-features",
        "fixture": fixture,
        "variant_id": variant_id,
        "capture_manifest_sha256": context.manifest_sha256,
        "capture_readiness_report_sha256": readiness.report_sha256,
        "capture_assessment_run_manifest_sha256": readiness.run_sha256,
        "model_policy_sha256": context.model_policy_sha256,
        "fall_feature_policy_sha256": config_sha256,
        "feature_version": feature_config.feature_version,
        "sample_fps": sample_fps,
        "input_paths_persisted": False,
        "labels_read_during_generation": False,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    project_dir = Path(__file__).resolve().parents[3]
    backend: PoseBackend | None = None
    try:
        with RunArtifacts(
            runs_dir,
            stage=FALL_FEATURE_CAPTURE_STAGE,
            evidence_level=evidence_level,
            configuration=configuration,
            project_dir=project_dir,
        ) as run:
            if run.manifest.started_at < context.first_inference_at:
                raise ValueError("feature source run precedes held-out first inference")
            source_specs = (
                (
                    capture_manifest_path,
                    "capture_manifest",
                    Modality.MULTIMODAL,
                    PrivacyLevel.RAW_SENSITIVE,
                    False,
                ),
                (
                    readiness.report_path,
                    "capture_readiness_report",
                    Modality.DEVICE_SNAPSHOT,
                    PrivacyLevel.AGGREGATE,
                    False,
                ),
                (
                    readiness.run_path,
                    "capture_assessment_run_manifest",
                    Modality.DEVICE_SNAPSHOT,
                    PrivacyLevel.AGGREGATE,
                    False,
                ),
                (
                    context.model_policy_path,
                    "pose_model_policy",
                    Modality.DEVICE_SNAPSHOT,
                    PrivacyLevel.AGGREGATE,
                    False,
                ),
                (
                    config_path,
                    "fall_feature_policy",
                    Modality.DEVICE_SNAPSHOT,
                    PrivacyLevel.AGGREGATE,
                    False,
                ),
            )
            recorded_asset_ids: set[str] = set()

            def record_asset_once(asset: SourceAsset) -> None:
                if asset.asset_id in recorded_asset_ids:
                    return
                run.record_asset(asset)
                recorded_asset_ids.add(asset.asset_id)

            for path, kind, modality, privacy, contains_raw_media in source_specs:
                record_asset_once(
                    _source_asset(
                        path,
                        kind=kind,
                        modality=modality,
                        source_type=source_type,
                        evidence_level=evidence_level,
                        privacy_level=privacy,
                        contains_raw_media=contains_raw_media,
                    )
                )
            for clip in context.clips:
                record_asset_once(
                    _source_asset(
                        clip.media_path,
                        kind="capture_media_clip",
                        modality=Modality.VIDEO,
                        source_type=source_type,
                        evidence_level=evidence_level,
                        privacy_level=PrivacyLevel.RAW_SENSITIVE,
                        contains_raw_media=True,
                    )
                )

            model_load_started = perf_counter()
            with run.step(f"load-capture-pose-backend:{variant_id}"):
                backend = backend_factory(context.model_policy_path)
                bindings, pose_binding, corrections = _validated_bindings(
                    variant_id=variant_id,
                    backend=backend,
                    model_policy_path=context.model_policy_path,
                )
            model_load_ms = (perf_counter() - model_load_started) * 1000.0
            clip_runtimes = [
                _run_clip(
                    context=context,
                    clip_index=index,
                    backend=backend,
                    pose_binding=pose_binding,
                    config_path=config_path,
                    run=run,
                    sample_fps=sample_fps,
                )
                for index in range(len(context.clips))
            ]
            if "features.jsonl" not in run.manifest.artifacts:
                run.manifest.artifacts.append("features.jsonl")
                run.save_manifest()

            with run.step("write-fall-feature-capture-set") as step:
                feature_set = FallFeatureCaptureSet(
                    feature_set_id=f"feature_set_{run.run_id}_{variant_id}",
                    fixture=fixture,
                    evidence_level=evidence_level,
                    variant_id=variant_id,
                    source_run_id=run.run_id,
                    capture_manifest_sha256=context.manifest_sha256,
                    model_policy_sha256=context.model_policy_sha256,
                    fall_feature_policy_sha256=config_sha256,
                    feature_version=feature_config.feature_version,
                    generated_at=utc_now(),
                    clip_count=len(clip_runtimes),
                    clips=[item.stream for item in clip_runtimes],
                    limitations=[
                        "largest_bbox_selection_is_single_primary_person_only",
                        "feature_output_is_not_a_risk_assessment_or_alert",
                    ],
                )
                feature_set_path = run.write_report(
                    "fall-feature-capture-set.json",
                    feature_set,
                )
                feature_set_sha256 = sha256_file(feature_set_path)
                run.manifest.configuration["fall_feature_set_sha256"] = (
                    feature_set_sha256
                )
                run.save_manifest()
                step.outputs.append(run.relative(feature_set_path))

            with run.step("write-fall-feature-capture-report") as step:
                report = FallFeatureCaptureReport(
                    producer_version=FALL_FEATURE_CAPTURE_PRODUCER_VERSION,
                    source_run_id=run.run_id,
                    fixture=fixture,
                    evidence_level=evidence_level,
                    capture_ref=context.capture_ref,
                    capture_manifest_sha256=context.manifest_sha256,
                    capture_readiness_report_sha256=readiness.report_sha256,
                    capture_assessment_run_id=readiness.run.run_id,
                    capture_assessment_run_manifest_sha256=readiness.run_sha256,
                    variant_id=variant_id,
                    model_policy_sha256=context.model_policy_sha256,
                    fall_feature_policy_sha256=config_sha256,
                    fall_feature_set_sha256=feature_set_sha256,
                    feature_version=feature_config.feature_version,
                    sample_fps=sample_fps,
                    model_bindings=bindings,
                    model_binding_license_corrections=corrections,
                    clip_count=len(clip_runtimes),
                    input_frame_count=sum(
                        item.report.sampled_frames for item in clip_runtimes
                    ),
                    clips=[item.report for item in clip_runtimes],
                    model_load_ms=round(model_load_ms, 3),
                    runtime_environment=_runtime_environment(),
                    limitations=[
                        "fixture_or_e1_output_is_tooling_evidence_only"
                        if fixture
                        else "e2_capture_output_still_requires_event_review",
                        "largest_bbox_selection_is_not_multi_person_identity_tracking",
                        "pose_and_fall_events_remain_derived_sensitive",
                        "candidate_risk_and_alert_layers_are_not_executed",
                    ],
                )
                report_path = run.write_report(
                    "fall-feature-capture-report.json",
                    report,
                )
                run.manifest.configuration[
                    "fall_feature_capture_report_sha256"
                ] = sha256_file(report_path)
                run.save_manifest()
                step.outputs.append(run.relative(report_path))
        return run, feature_set, report
    finally:
        backend = None
        _release_backend()
