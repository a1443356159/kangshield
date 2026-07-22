from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from pydantic import ValidationError

from .artifacts import RunArtifacts
from .contracts import (
    EVIDENCE_RANK,
    EvidenceLevel,
    FallCandidateExportSummary,
    FallCandidatePredictionClip,
    FallCandidatePredictionEvent,
    FallCandidatePredictionSet,
    FallEventCandidateEpisode,
    FallEventCandidatePolicy,
    FallFeatureCaptureSet,
    FallFeatureClipStream,
    FallMotionFrameValue,
    FeatureEvent,
    Modality,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    SourceAsset,
    SourceType,
    utc_now,
)
from .fall_candidates import (
    generate_fall_candidate_episodes,
    load_fall_candidate_policy,
)
from .m2c_capture import M2cEventContext, load_m2c_event_context
from .privacy import safe_local_uri, sha256_file


FALL_FEATURE_CAPTURE_STAGE = "v1-g4-fall-feature-capture"
FALL_CANDIDATE_SOURCE_STAGE = "v1-g4-fall-event-candidates"
FALL_CANDIDATE_EXPORTER_VERSION = "fall-candidate-export-v0.1.0"


@dataclass(frozen=True)
class _VerifiedFeatureSource:
    context: M2cEventContext
    feature_set: FallFeatureCaptureSet
    feature_set_path: Path
    feature_set_sha256: str
    source_run: RunManifest
    source_run_path: Path
    source_run_sha256: str
    policy: FallEventCandidatePolicy
    policy_path: Path
    policy_sha256: str
    streams: tuple[tuple[FallFeatureClipStream, Path, tuple[FeatureEvent, ...]], ...]


def _load_json(path: Path, model: type, *, kind: str):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{kind} could not be read as JSON") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"{kind} schema validation failed") from error


def _safe_run_path(run_dir: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in relative_path
    ):
        raise ValueError("feature stream path must be normalized and relative")
    root = run_dir.resolve()
    resolved = (root / Path(*pure.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("feature stream path escapes its source run")
    return resolved


def _source_asset(
    path: Path,
    *,
    kind: str,
    modality: Modality,
    source_type: SourceType,
    evidence_level: EvidenceLevel,
    privacy_level: PrivacyLevel,
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
            "contains_raw_media": False,
            "source_path_persisted": False,
        },
    )


def _validate_source_run(
    manifest: RunManifest,
    *,
    expected: dict[str, object],
    evidence_level: EvidenceLevel,
    feature_set: FallFeatureCaptureSet,
    allow_dirty_source: bool,
) -> None:
    if manifest.stage != FALL_FEATURE_CAPTURE_STAGE:
        raise ValueError("fall feature source run stage is invalid")
    if manifest.status is not RunStatus.COMPLETED or manifest.finished_at is None:
        raise ValueError("fall feature source run is not completed")
    if manifest.evidence_level is not evidence_level:
        raise ValueError("fall feature source evidence level disagrees")
    if manifest.code_version == "unknown":
        raise ValueError("fall feature source code version is unknown")
    if manifest.code_dirty and not allow_dirty_source:
        raise ValueError("fall feature source run is dirty")
    if any(issue.severity.value == "error" for issue in manifest.issues):
        raise ValueError("fall feature source run contains an error issue")
    if manifest.started_at.utcoffset() is None or manifest.finished_at.utcoffset() is None:
        raise ValueError("fall feature source run timestamps require timezones")
    if not manifest.started_at <= feature_set.generated_at <= manifest.finished_at:
        raise ValueError("fall feature set timestamp is outside its source run")
    if any(manifest.configuration.get(key) != value for key, value in expected.items()):
        raise ValueError("fall feature source run configuration disagrees")


def _read_feature_stream(
    path: Path,
    *,
    clip: FallFeatureClipStream,
    feature_version: str,
) -> tuple[FeatureEvent, ...]:
    events: list[FeatureEvent] = []
    feature_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("fall feature stream could not be read") from error
    for line in lines:
        if not line.strip():
            continue
        try:
            event = FeatureEvent.model_validate_json(line)
            value = FallMotionFrameValue.model_validate(event.value)
        except ValidationError as error:
            raise ValueError("fall feature stream schema validation failed") from error
        if event.feature_type != "video.fall_motion_frame":
            raise ValueError("fall feature stream contains another feature type")
        if event.feature_id in feature_ids:
            raise ValueError("fall feature stream contains duplicate feature ids")
        if event.observation_id != clip.observation_id:
            raise ValueError("fall feature observation differs from feature set")
        if value.feature_version != feature_version:
            raise ValueError("fall feature version differs from feature set")
        if event.extractor_version != value.feature_version:
            raise ValueError("fall feature extractor version is inconsistent")
        if event.time_range.start_ms != value.timestamp_ms:
            raise ValueError("fall feature timestamp differs from its time range")
        if (
            event.time_range.end_ms is None
            or event.time_range.end_ms <= value.timestamp_ms
            or event.time_range.end_ms > clip.duration_ms
        ):
            raise ValueError("fall feature frame window is outside clip duration")
        if event.privacy_level is not PrivacyLevel.DERIVED_SENSITIVE:
            raise ValueError("fall feature stream must remain derived-sensitive")
        feature_ids.add(event.feature_id)
        events.append(event)
    if len(events) != clip.frame_count:
        raise ValueError("fall feature stream frame count disagrees")
    return tuple(events)


def _verify_inputs(
    *,
    capture_manifest_path: Path,
    feature_set_path: Path,
    source_feature_run_manifest_path: Path,
    policy_path: Path,
    evidence_level: EvidenceLevel,
    allow_dirty_source: bool,
) -> _VerifiedFeatureSource:
    capture_manifest_path = Path(capture_manifest_path).resolve()
    feature_set_path = Path(feature_set_path).resolve()
    source_run_path = Path(source_feature_run_manifest_path).resolve()
    policy_path = Path(policy_path).resolve()
    for path, kind in (
        (capture_manifest_path, "capture manifest"),
        (feature_set_path, "fall feature set"),
        (source_run_path, "fall feature source run"),
        (policy_path, "candidate policy"),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{kind} not found")

    context = load_m2c_event_context(capture_manifest_path)
    if context.first_inference_at is None:
        raise ValueError("capture held-out protocol has no first inference timestamp")
    feature_set = _load_json(
        feature_set_path,
        FallFeatureCaptureSet,
        kind="fall feature set",
    )
    source_run = _load_json(
        source_run_path,
        RunManifest,
        kind="fall feature source run",
    )
    policy = load_fall_candidate_policy(policy_path, allow_fixture=True)
    policy_sha256 = sha256_file(policy_path)
    feature_set_sha256 = sha256_file(feature_set_path)
    source_run_sha256 = sha256_file(source_run_path)

    if feature_set.fixture != policy.fixture:
        raise ValueError("feature set fixture marker differs from candidate policy")
    if feature_set.fixture:
        if evidence_level is not EvidenceLevel.E1:
            raise ValueError("fixture candidate export must remain E1")
        if not (context.synthetic or context.template_only):
            raise ValueError("fixture feature set requires a fixture capture")
    elif context.synthetic or context.template_only:
        raise ValueError("non-fixture feature set cannot use a fixture capture")
    if feature_set.evidence_level is not evidence_level:
        raise ValueError("fall feature set evidence level disagrees")
    if feature_set.capture_manifest_sha256 != context.manifest_sha256:
        raise ValueError("fall feature set refers to another capture manifest")
    model_policies = dict(context.model_policy_sha256s)
    if model_policies.get(feature_set.variant_id) != feature_set.model_policy_sha256:
        raise ValueError("fall feature set model policy differs from capture")
    if (
        feature_set.fall_feature_policy_sha256
        != policy.input_fall_feature_policy_sha256
    ):
        raise ValueError("fall feature set policy differs from candidate input")
    if feature_set.feature_version != policy.input_fall_feature_version:
        raise ValueError("fall feature set version differs from candidate input")
    expected_clips = [
        (clip.scenario_id, clip.duration_ms) for clip in context.clips
    ]
    observed_clips = [
        (clip.scenario_id, clip.duration_ms) for clip in feature_set.clips
    ]
    if observed_clips != expected_clips:
        raise ValueError("fall feature set clip order or duration differs from capture")

    if source_run_path.name != "manifest.json":
        raise ValueError("fall feature source run must use manifest.json")
    source_run_dir = source_run_path.parent.resolve()
    if source_run.run_id != feature_set.source_run_id:
        raise ValueError("fall feature set source run id disagrees")
    if source_run_dir.name != source_run.run_id:
        raise ValueError("fall feature source directory disagrees with run id")
    if not feature_set_path.is_relative_to(source_run_dir):
        raise ValueError("fall feature set is outside its source run")
    feature_set_relative = feature_set_path.relative_to(source_run_dir).as_posix()
    expected_configuration = {
        "variant_id": feature_set.variant_id,
        "capture_manifest_sha256": context.manifest_sha256,
        "model_policy_sha256": feature_set.model_policy_sha256,
        "fall_feature_policy_sha256": feature_set.fall_feature_policy_sha256,
        "fall_feature_set_sha256": feature_set_sha256,
        "feature_version": feature_set.feature_version,
        "labels_read_during_generation": False,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    _validate_source_run(
        source_run,
        expected=expected_configuration,
        evidence_level=evidence_level,
        feature_set=feature_set,
        allow_dirty_source=allow_dirty_source,
    )
    if source_run.started_at < context.first_inference_at:
        raise ValueError("fall feature source run precedes held-out first inference")
    if source_run.started_at < context.labels_frozen_at:
        raise ValueError("fall feature source run precedes frozen labels")
    if feature_set_relative not in source_run.artifacts:
        raise ValueError("fall feature source manifest does not bind its feature set")

    streams: list[tuple[FallFeatureClipStream, Path, tuple[FeatureEvent, ...]]] = []
    for clip in feature_set.clips:
        path = _safe_run_path(source_run_dir, clip.relative_path)
        if not path.is_file():
            raise ValueError("referenced fall feature stream is missing")
        if path.stat().st_size != clip.byte_size:
            raise ValueError("fall feature stream byte size differs from feature set")
        if sha256_file(path) != clip.sha256:
            raise ValueError("fall feature stream digest differs from feature set")
        if clip.relative_path not in source_run.artifacts:
            raise ValueError("fall feature source manifest does not bind a stream")
        events = _read_feature_stream(
            path,
            clip=clip,
            feature_version=feature_set.feature_version,
        )
        streams.append((clip, path, events))
    return _VerifiedFeatureSource(
        context=context,
        feature_set=feature_set,
        feature_set_path=feature_set_path,
        feature_set_sha256=feature_set_sha256,
        source_run=source_run,
        source_run_path=source_run_path,
        source_run_sha256=source_run_sha256,
        policy=policy,
        policy_path=policy_path,
        policy_sha256=policy_sha256,
        streams=tuple(streams),
    )


def _episodes(
    verified: _VerifiedFeatureSource,
) -> tuple[tuple[FallFeatureClipStream, tuple[FallEventCandidateEpisode, ...]], ...]:
    generated = []
    for clip, _, events in verified.streams:
        values = [FallMotionFrameValue.model_validate(event.value) for event in events]
        episodes = generate_fall_candidate_episodes(
            values,
            duration_ms=clip.duration_ms,
            case_ref=(
                f"{verified.context.capture_ref}:"
                f"{verified.feature_set.variant_id}:{clip.scenario_id}"
            ),
            policy=verified.policy,
        )
        generated.append((clip, tuple(episodes)))
    return tuple(generated)


def _assets(
    verified: _VerifiedFeatureSource,
    *,
    capture_manifest_path: Path,
    evidence_level: EvidenceLevel,
) -> Iterable[SourceAsset]:
    source_type = (
        SourceType.FIXTURE if verified.feature_set.fixture else SourceType.LOCAL_FILE
    )
    yield _source_asset(
        capture_manifest_path,
        kind="capture_manifest",
        modality=Modality.MULTIMODAL,
        source_type=source_type,
        evidence_level=evidence_level,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
    )
    for path, kind, modality, privacy in (
        (
            verified.feature_set_path,
            "fall_feature_capture_set",
            Modality.VIDEO,
            PrivacyLevel.AGGREGATE,
        ),
        (
            verified.source_run_path,
            "fall_feature_source_run_manifest",
            Modality.DEVICE_SNAPSHOT,
            PrivacyLevel.AGGREGATE,
        ),
        (
            verified.policy_path,
            "fall_candidate_policy",
            Modality.DEVICE_SNAPSHOT,
            PrivacyLevel.AGGREGATE,
        ),
    ):
        yield _source_asset(
            path,
            kind=kind,
            modality=modality,
            source_type=source_type,
            evidence_level=evidence_level,
            privacy_level=privacy,
        )
    for _, path, _ in verified.streams:
        yield _source_asset(
            path,
            kind="fall_feature_frame_stream",
            modality=Modality.VIDEO,
            source_type=source_type,
            evidence_level=evidence_level,
            privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        )


def run_fall_candidate_export(
    *,
    capture_manifest_path: Path,
    feature_set_path: Path,
    source_feature_run_manifest_path: Path,
    policy_path: Path,
    runs_dir: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    allow_dirty_source: bool = False,
) -> tuple[RunArtifacts, FallCandidatePredictionSet, FallCandidateExportSummary]:
    """Export capture-bound candidate episodes for the held-out evaluator."""

    verified = _verify_inputs(
        capture_manifest_path=capture_manifest_path,
        feature_set_path=feature_set_path,
        source_feature_run_manifest_path=source_feature_run_manifest_path,
        policy_path=policy_path,
        evidence_level=evidence_level,
        allow_dirty_source=allow_dirty_source,
    )
    if EVIDENCE_RANK[evidence_level] > EVIDENCE_RANK[EvidenceLevel.E2]:
        raise ValueError("local candidate export can provide at most E2 evidence")
    generated = _episodes(verified)
    configuration = {
        "command": "export-fall-candidates",
        "fixture": verified.feature_set.fixture,
        "variant_id": verified.feature_set.variant_id,
        "capture_manifest_sha256": verified.context.manifest_sha256,
        "model_policy_sha256": verified.feature_set.model_policy_sha256,
        "fall_feature_policy_sha256": (
            verified.feature_set.fall_feature_policy_sha256
        ),
        "candidate_generator_policy_sha256": verified.policy_sha256,
        "source_feature_run_id": verified.source_run.run_id,
        "source_feature_run_manifest_sha256": verified.source_run_sha256,
        "source_feature_set_sha256": verified.feature_set_sha256,
        "input_paths_persisted": False,
        "labels_read_during_generation": False,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    project_dir = Path(__file__).resolve().parents[3]
    with RunArtifacts(
        runs_dir,
        stage=FALL_CANDIDATE_SOURCE_STAGE,
        evidence_level=evidence_level,
        configuration=configuration,
        project_dir=project_dir,
    ) as run:
        for asset in _assets(
            verified,
            capture_manifest_path=Path(capture_manifest_path).resolve(),
            evidence_level=evidence_level,
        ):
            run.record_asset(asset)
        with run.step("export-fall-candidates") as step:
            prediction = FallCandidatePredictionSet(
                prediction_set_id=(
                    f"prediction_{run.run_id}_{verified.feature_set.variant_id}"
                ),
                variant_id=verified.feature_set.variant_id,
                source_run_id=run.run_id,
                capture_manifest_sha256=verified.context.manifest_sha256,
                model_policy_sha256=verified.feature_set.model_policy_sha256,
                fall_feature_policy_sha256=(
                    verified.feature_set.fall_feature_policy_sha256
                ),
                candidate_generator_policy_sha256=verified.policy_sha256,
                generated_at=utc_now(),
                clips=[
                    FallCandidatePredictionClip(
                        scenario_id=clip.scenario_id,
                        duration_ms=clip.duration_ms,
                        candidates=[
                            FallCandidatePredictionEvent(
                                candidate_id=episode.candidate_id,
                                start_ms=episode.start_ms,
                                end_ms=episode.end_ms,
                                detected_at_ms=episode.detected_at_ms,
                            )
                            for episode in episodes
                        ],
                    )
                    for clip, episodes in generated
                ],
            )
            prediction_path = run.write_report(
                "fall-candidate-predictions.json",
                prediction,
            )
            candidate_events_sha256 = sha256_file(prediction_path)
            run.manifest.configuration["candidate_events_sha256"] = (
                candidate_events_sha256
            )
            run.save_manifest()
            all_episodes = [
                episode for _, episodes in generated for episode in episodes
            ]
            summary = FallCandidateExportSummary(
                exporter_version=FALL_CANDIDATE_EXPORTER_VERSION,
                fixture=verified.feature_set.fixture,
                evidence_level=evidence_level,
                capture_ref=verified.context.capture_ref,
                variant_id=verified.feature_set.variant_id,
                source_feature_run_id=verified.source_run.run_id,
                source_feature_run_manifest_sha256=verified.source_run_sha256,
                source_feature_set_sha256=verified.feature_set_sha256,
                model_policy_sha256=verified.feature_set.model_policy_sha256,
                fall_feature_policy_sha256=(
                    verified.feature_set.fall_feature_policy_sha256
                ),
                candidate_generator_policy_sha256=verified.policy_sha256,
                candidate_events_sha256=candidate_events_sha256,
                clip_count=len(generated),
                input_frame_count=sum(
                    len(events) for _, _, events in verified.streams
                ),
                activated_clip_count=sum(bool(episodes) for _, episodes in generated),
                candidate_episode_count=len(all_episodes),
                transition_trigger_count=sum(
                    episode.trigger_path == "rapid_descent_then_horizontal"
                    for episode in all_episodes
                ),
                settled_trigger_count=sum(
                    episode.trigger_path == "settled_horizontal_low_motion"
                    for episode in all_episodes
                ),
                limitations=[
                    "candidate_episodes_are_not_risk_assessments_or_alerts",
                    "source_frames_remain_derived_sensitive",
                    "held_out_labels_are_not_read_during_generation",
                ],
            )
            summary_path = run.write_report(
                "fall-candidate-export-summary.json",
                summary,
            )
            step.outputs.extend(
                (run.relative(prediction_path), run.relative(summary_path))
            )
    return run, prediction, summary
