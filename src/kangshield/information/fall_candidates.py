from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from .artifacts import RunArtifacts
from .contracts import (
    DatasetBenchmarkCase,
    EvidenceLevel,
    FallAdlBenchmarkReport,
    FallAdlCaseEvaluation,
    FallCandidateCaseStressEvaluation,
    FallCandidatePublicStressReport,
    FallCandidateVariantStressReport,
    FallEventCandidateEpisode,
    FallEventCandidatePolicy,
    FallFeatureBenchmarkReport,
    FallMotionFrameValue,
    FeatureEvent,
    Modality,
    PrivacyLevel,
    RunManifest,
    RunStatus,
    SourceAsset,
    SourceType,
    TimeRange,
)
from .dataset_benchmark import load_benchmark_cases
from .fall_adl_preparation import (
    EXPECTED_DATASET_DOI,
    EXPECTED_DATASET_ID,
    EXPECTED_DATASET_LICENSE,
    EXPECTED_DATASET_VERSION,
)
from .privacy import safe_local_uri, sha256_file


FALL_CANDIDATE_BENCHMARK_VERSION = "fall-candidate-public-stress-v0.1.0"
FALL_CANDIDATE_EXTRACTOR = "kangshield-fall-event-candidates"
KNOWN_VARIANTS = (
    "yolo26n-pose",
    "rtmpose-m-humanart",
    "torchvision-keypointrcnn",
)


@dataclass(frozen=True)
class _FallFrame:
    event: FeatureEvent
    value: FallMotionFrameValue


@dataclass(frozen=True)
class _SourceFile:
    path: Path
    kind: str
    privacy_level: PrivacyLevel


@dataclass(frozen=True)
class _UrfdSource:
    run_dir: Path
    manifest_path: Path
    report_path: Path
    features_path: Path
    manifest: RunManifest
    report: FallFeatureBenchmarkReport
    frames_by_case: dict[str, list[_FallFrame]]
    source_files: list[_SourceFile]


@dataclass(frozen=True)
class _CaucafallSource:
    run_dir: Path
    manifest_path: Path
    report_path: Path
    manifest: RunManifest
    report: FallAdlBenchmarkReport
    frames_by_variant_case: dict[tuple[str, str], list[_FallFrame]]
    source_files: list[_SourceFile]


@dataclass
class _OpenEpisode:
    start_ms: int
    detected_at_ms: int
    last_horizontal_ms: int
    trigger_path: str


def load_fall_candidate_policy(
    path: Path,
    *,
    allow_fixture: bool = False,
) -> FallEventCandidatePolicy:
    policy = FallEventCandidatePolicy.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    if policy.fixture and not allow_fixture:
        raise ValueError("public candidate generation requires a non-fixture policy")
    return policy


def generate_fall_candidate_episodes(
    frames: Iterable[FallMotionFrameValue],
    *,
    duration_ms: int,
    case_ref: str,
    policy: FallEventCandidatePolicy,
) -> list[FallEventCandidateEpisode]:
    """Generate candidates from frame proxies only; no labels enter this API."""

    if duration_ms <= 0:
        raise ValueError("candidate input duration must be positive")
    if policy.fixture:
        if policy.review_status != "fixture_only":
            raise ValueError("fixture candidate generation requires fixture-only review")
    elif policy.review_status != "e1_exploratory_frozen":
        raise ValueError("candidate generation requires a frozen non-fixture policy")
    transition = policy.transition_rule
    settled = policy.settled_rule
    machine = policy.state_machine
    if transition is None or settled is None or machine is None:
        raise ValueError("candidate policy is missing generation rules")

    values = list(frames)
    if not values:
        raise ValueError("candidate generation requires at least one frame")
    previous_timestamp: int | None = None
    previous_sequence: int | None = None
    frame_size: tuple[int, int] | None = None
    for value in values:
        if value.feature_version != policy.input_fall_feature_version:
            raise ValueError("fall frame feature version differs from candidate policy")
        if value.risk_assessment_emitted or value.alert_emitted:
            raise ValueError("candidate input must not contain risk or alert output")
        if value.timestamp_ms >= duration_ms:
            raise ValueError("fall frame timestamp must remain inside clip duration")
        if previous_timestamp is not None and value.timestamp_ms <= previous_timestamp:
            raise ValueError("fall frame timestamps must be strictly increasing")
        if previous_sequence is not None and value.frame_sequence <= previous_sequence:
            raise ValueError("fall frame sequences must be strictly increasing")
        size = (value.frame_width, value.frame_height)
        if frame_size is not None and size != frame_size:
            raise ValueError("fall frame dimensions cannot change within a clip")
        frame_size = size
        previous_timestamp = value.timestamp_ms
        previous_sequence = value.frame_sequence

    episodes: list[FallEventCandidateEpisode] = []
    open_episode: _OpenEpisode | None = None
    current_track_id: int | None = None
    previous_timestamp = None
    rapid_descent_timestamps: list[int] = []
    refractory_until_ms = -1
    case_digest = sha256(case_ref.encode("utf-8")).hexdigest()[:12]

    def close_episode(requested_end_ms: int) -> None:
        nonlocal open_episode, rapid_descent_timestamps, refractory_until_ms
        if open_episode is None:
            return
        end_ms = min(
            duration_ms,
            max(open_episode.detected_at_ms + 1, requested_end_ms),
        )
        episode = FallEventCandidateEpisode(
            candidate_version=policy.candidate_event_version,
            candidate_id=f"candidate_{case_digest}_{len(episodes):03d}",
            start_ms=open_episode.start_ms,
            detected_at_ms=open_episode.detected_at_ms,
            end_ms=end_ms,
            trigger_path=open_episode.trigger_path,
        )
        if episodes and episode.start_ms < episodes[-1].end_ms:
            raise ValueError("candidate episodes overlap after deduplication")
        episodes.append(episode)
        refractory_until_ms = end_ms + machine.refractory_ms
        rapid_descent_timestamps = []
        open_episode = None

    for value in values:
        timestamp_ms = value.timestamp_ms
        track_id = value.selected_track_id
        boundary = (
            previous_timestamp is not None
            and timestamp_ms - previous_timestamp > machine.max_frame_gap_ms
        )
        track_changed = (
            current_track_id is not None
            and track_id is not None
            and track_id != current_track_id
        )
        track_missing = track_id is None
        if boundary or track_changed or track_missing:
            if open_episode is not None:
                close_episode(
                    open_episode.last_horizontal_ms + machine.release_grace_ms
                )
            rapid_descent_timestamps = []
            current_track_id = None

        if track_missing:
            previous_timestamp = timestamp_ms
            continue
        if current_track_id is None:
            current_track_id = track_id

        if (
            open_episode is not None
            and timestamp_ms
            > open_episode.last_horizontal_ms + machine.release_grace_ms
        ):
            close_episode(
                open_episode.last_horizontal_ms + machine.release_grace_ms
            )

        cutoff = timestamp_ms - transition.rapid_descent_lookback_ms
        rapid_descent_timestamps = [
            item for item in rapid_descent_timestamps if item >= cutoff
        ]
        if value.rapid_descent_proxy is True:
            rapid_descent_timestamps.append(timestamp_ms)

        horizontal = value.bbox_horizontal_proxy is True
        if horizontal and value.horizontal_duration_ms is None:
            raise ValueError("horizontal frame is missing horizontal duration")
        if open_episode is not None and horizontal:
            open_episode.last_horizontal_ms = timestamp_ms

        if open_episode is None and timestamp_ms >= refractory_until_ms and horizontal:
            horizontal_duration_ms = value.horizontal_duration_ms or 0
            transition_ready = (
                horizontal_duration_ms
                >= transition.minimum_horizontal_duration_ms
                and bool(rapid_descent_timestamps)
                and (
                    not transition.low_motion_required
                    or value.low_motion_proxy is True
                )
            )
            settled_ready = (
                horizontal_duration_ms >= settled.minimum_horizontal_duration_ms
                and value.low_motion_proxy is True
            )
            if transition_ready:
                open_episode = _OpenEpisode(
                    start_ms=rapid_descent_timestamps[0],
                    detected_at_ms=timestamp_ms,
                    last_horizontal_ms=timestamp_ms,
                    trigger_path="rapid_descent_then_horizontal",
                )
            elif settled_ready:
                open_episode = _OpenEpisode(
                    start_ms=max(0, timestamp_ms - horizontal_duration_ms),
                    detected_at_ms=timestamp_ms,
                    last_horizontal_ms=timestamp_ms,
                    trigger_path="settled_horizontal_low_motion",
                )

        previous_timestamp = timestamp_ms

    if open_episode is not None:
        close_episode(open_episode.last_horizontal_ms + machine.release_grace_ms)
    return episodes


def _read_fall_frames(
    path: Path,
    *,
    expected_feature_version: str,
) -> list[_FallFrame]:
    frames: list[_FallFrame] = []
    feature_ids: set[str] = set()
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            event = FeatureEvent.model_validate_json(line)
            if event.feature_type != "video.fall_motion_frame":
                continue
            if event.feature_id in feature_ids:
                raise ValueError("fall feature stream contains duplicate feature ids")
            feature_ids.add(event.feature_id)
            value = FallMotionFrameValue.model_validate(event.value)
            if value.feature_version != expected_feature_version:
                raise ValueError("fall feature stream version differs from source report")
            if event.extractor_version != value.feature_version:
                raise ValueError("fall feature extractor version is inconsistent")
            if event.time_range.start_ms != value.timestamp_ms:
                raise ValueError("fall feature timestamp differs from its time range")
            if event.privacy_level is not PrivacyLevel.DERIVED_SENSITIVE:
                raise ValueError("fall feature must remain derived-sensitive")
            frames.append(_FallFrame(event=event, value=value))
    if not frames:
        raise ValueError("source feature stream contains no fall motion frames")
    return frames


def _require_clean_completed_run(
    manifest: RunManifest,
    *,
    run_dir: Path,
    expected_stage: str,
    allow_dirty_source: bool,
) -> None:
    if manifest.run_id != run_dir.name:
        raise ValueError("source manifest run id differs from its directory")
    if manifest.stage != expected_stage:
        raise ValueError("source manifest has the wrong stage")
    if manifest.status is not RunStatus.COMPLETED:
        raise ValueError("source run is not completed")
    if manifest.evidence_level is not EvidenceLevel.E1:
        raise ValueError("source run must remain E1")
    if manifest.code_dirty and not allow_dirty_source:
        raise ValueError("source run is dirty")
    if any(issue.severity.value == "error" for issue in manifest.issues):
        raise ValueError("source run contains an error issue")


def _load_urfd_source(
    run_dir: Path,
    *,
    policy: FallEventCandidatePolicy,
    allow_dirty_source: bool,
) -> _UrfdSource:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "reports" / "fall-feature-benchmark-report.json"
    features_path = run_dir / "features.jsonl"
    if not all(path.is_file() for path in (manifest_path, report_path, features_path)):
        raise FileNotFoundError("URFD fall-feature source run is incomplete")
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    report = FallFeatureBenchmarkReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    _require_clean_completed_run(
        manifest,
        run_dir=run_dir,
        expected_stage="v1-g4-fall-feature-benchmark",
        allow_dirty_source=allow_dirty_source,
    )
    if report.evidence_level is not EvidenceLevel.E1:
        raise ValueError("URFD fall-feature report must remain E1")
    if report.source_pose_code_dirty and not allow_dirty_source:
        raise ValueError("URFD source pose run was dirty")
    if report.configuration_sha256 != policy.input_fall_feature_policy_sha256:
        raise ValueError("URFD fall-feature policy digest differs from candidate policy")
    expected_configuration = {
        "benchmark_id": report.benchmark_id,
        "variant_id": report.variant_id,
        "feature_version": report.feature_version,
        "configuration_sha256": report.configuration_sha256,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    for field, expected in expected_configuration.items():
        if manifest.configuration.get(field) != expected:
            raise ValueError(f"URFD source manifest {field} disagrees with report")
    if report.risk_assessment_emitted or report.alert_emitted:
        raise ValueError("URFD fall-feature report emitted risk or alert")
    if report.case_count != len(report.cases):
        raise ValueError("URFD fall-feature report case count is inconsistent")
    if "reports/fall-feature-benchmark-report.json" not in manifest.artifacts:
        raise ValueError("URFD source manifest does not bind its report")

    frames = _read_fall_frames(
        features_path,
        expected_feature_version=report.feature_version,
    )
    by_observation: dict[str, list[_FallFrame]] = {}
    for frame in frames:
        by_observation.setdefault(frame.event.observation_id, []).append(frame)
    frames_by_case: dict[str, list[_FallFrame]] = {}
    expected_observations: set[str] = set()
    for case in report.cases:
        observation_id = f"observation_{case.source_pose_run_id}_video"
        expected_observations.add(observation_id)
        case_frames = by_observation.get(observation_id, [])
        if len(case_frames) != case.sampled_frames:
            raise ValueError(f"URFD source frame count mismatch: {case.case_id}")
        frames_by_case[case.case_id] = case_frames
    if set(by_observation) != expected_observations:
        raise ValueError("URFD feature stream contains an unexpected observation")
    if sum(len(items) for items in frames_by_case.values()) != len(frames):
        raise ValueError("URFD feature stream case accounting is inconsistent")
    return _UrfdSource(
        run_dir=run_dir,
        manifest_path=manifest_path,
        report_path=report_path,
        features_path=features_path,
        manifest=manifest,
        report=report,
        frames_by_case=frames_by_case,
        source_files=[
            _SourceFile(manifest_path, "urfd_fall_feature_run_manifest", PrivacyLevel.AGGREGATE),
            _SourceFile(report_path, "urfd_fall_feature_report", PrivacyLevel.AGGREGATE),
            _SourceFile(features_path, "urfd_fall_feature_events", PrivacyLevel.DERIVED_SENSITIVE),
        ],
    )


def _load_caucafall_source(
    run_dir: Path,
    *,
    policy: FallEventCandidatePolicy,
    allow_dirty_source: bool,
) -> _CaucafallSource:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "reports" / "fall-adl-benchmark-report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        raise FileNotFoundError("CAUCAFall source parent run is incomplete")
    manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    report = FallAdlBenchmarkReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    _require_clean_completed_run(
        manifest,
        run_dir=run_dir,
        expected_stage="v1-g4-fall-adl-negative-benchmark",
        allow_dirty_source=allow_dirty_source,
    )
    if report.configuration_sha256 != policy.input_fall_feature_policy_sha256:
        raise ValueError("CAUCAFall feature policy digest differs from candidate policy")
    expected_dataset = (
        EXPECTED_DATASET_ID,
        EXPECTED_DATASET_VERSION,
        EXPECTED_DATASET_DOI,
        EXPECTED_DATASET_LICENSE,
    )
    observed_dataset = (
        report.dataset_id,
        report.dataset_version,
        report.dataset_doi,
        report.dataset_license,
    )
    if observed_dataset != expected_dataset:
        raise ValueError("CAUCAFall source dataset provenance has drifted")
    expected_configuration = {
        "suite_id": report.suite_id,
        "feature_version": report.feature_version,
        "configuration_sha256": report.configuration_sha256,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }
    for field, expected in expected_configuration.items():
        if manifest.configuration.get(field) != expected:
            raise ValueError(f"CAUCAFall source manifest {field} disagrees with report")
    if manifest.configuration.get("variants") != [
        variant.variant_id for variant in report.variants
    ]:
        raise ValueError("CAUCAFall source variant order differs from manifest")
    if report.risk_assessment_emitted or report.alert_emitted:
        raise ValueError("CAUCAFall source report emitted risk or alert")
    if "reports/fall-adl-benchmark-report.json" not in manifest.artifacts:
        raise ValueError("CAUCAFall source manifest does not bind its report")

    runs_dir = run_dir.parent
    frames_by_variant_case: dict[tuple[str, str], list[_FallFrame]] = {}
    source_files = [
        _SourceFile(manifest_path, "caucafall_parent_run_manifest", PrivacyLevel.AGGREGATE),
        _SourceFile(report_path, "caucafall_parent_report", PrivacyLevel.AGGREGATE),
    ]
    child_ids: set[str] = set()
    for variant in report.variants:
        for parent_case in variant.cases:
            child_id = parent_case.run_id
            if Path(child_id).name != child_id or child_id in child_ids:
                raise ValueError("CAUCAFall child run id is invalid or duplicated")
            child_ids.add(child_id)
            child_dir = (runs_dir / child_id).resolve()
            if child_dir.parent != runs_dir.resolve():
                raise ValueError("CAUCAFall child run escapes runs directory")
            child_manifest_path = child_dir / "manifest.json"
            child_report_path = child_dir / "reports" / "fall-adl-case-evaluation.json"
            child_features_path = child_dir / "features.jsonl"
            if not all(
                path.is_file()
                for path in (
                    child_manifest_path,
                    child_report_path,
                    child_features_path,
                )
            ):
                raise FileNotFoundError(f"CAUCAFall child run is incomplete: {child_id}")
            child_manifest = RunManifest.model_validate_json(
                child_manifest_path.read_text(encoding="utf-8")
            )
            child_report = FallAdlCaseEvaluation.model_validate_json(
                child_report_path.read_text(encoding="utf-8")
            )
            _require_clean_completed_run(
                child_manifest,
                run_dir=child_dir,
                expected_stage="v1-g4-fall-adl-negative-case",
                allow_dirty_source=allow_dirty_source,
            )
            if child_manifest.code_version != manifest.code_version:
                raise ValueError("CAUCAFall child code version differs from parent")
            if child_report.model_dump(mode="json") != parent_case.model_dump(mode="json"):
                raise ValueError("CAUCAFall child report differs from parent summary")
            child_expected = {
                "variant_id": variant.variant_id,
                "case_id": parent_case.case_id,
                "source_video_sha256": parent_case.source_video_sha256,
                "risk_assessment_emitted": False,
                "alert_emitted": False,
            }
            for field, expected in child_expected.items():
                if child_manifest.configuration.get(field) != expected:
                    raise ValueError(
                        f"CAUCAFall child manifest {field} disagrees with report"
                    )
            if "reports/fall-adl-case-evaluation.json" not in child_manifest.artifacts:
                raise ValueError("CAUCAFall child manifest does not bind its report")
            frames = _read_fall_frames(
                child_features_path,
                expected_feature_version=report.feature_version,
            )
            if len(frames) != parent_case.sampled_frames:
                raise ValueError("CAUCAFall child fall-feature count disagrees")
            if any(
                frame.event.observation_id != f"observation_{child_id}_video"
                for frame in frames
            ):
                raise ValueError("CAUCAFall child feature observation is inconsistent")
            key = (variant.variant_id, parent_case.case_id)
            if key in frames_by_variant_case:
                raise ValueError("CAUCAFall variant/case binding is duplicated")
            frames_by_variant_case[key] = frames
            source_files.extend(
                [
                    _SourceFile(child_manifest_path, "caucafall_child_run_manifest", PrivacyLevel.AGGREGATE),
                    _SourceFile(child_report_path, "caucafall_child_report", PrivacyLevel.AGGREGATE),
                    _SourceFile(child_features_path, "caucafall_child_feature_events", PrivacyLevel.DERIVED_SENSITIVE),
                ]
            )
    return _CaucafallSource(
        run_dir=run_dir,
        manifest_path=manifest_path,
        report_path=report_path,
        manifest=manifest,
        report=report,
        frames_by_variant_case=frames_by_variant_case,
        source_files=source_files,
    )


def _source_asset(source: _SourceFile) -> SourceAsset:
    digest = sha256_file(source.path)
    return SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=Modality.VIDEO,
        source_type=SourceType.LOCAL_FILE,
        evidence_level=EvidenceLevel.E1,
        uri=safe_local_uri(source.path, digest),
        sha256=digest,
        byte_size=source.path.stat().st_size,
        privacy_level=source.privacy_level,
        metadata={
            "kind": source.kind,
            "filename_suffix": source.path.suffix.lower(),
            "contains_raw_media": False,
            "source_path_persisted": False,
        },
    )


def _safe_suite_path(suite_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("benchmark annotation path must remain relative")
    root = Path(suite_path).parent.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("benchmark annotation path escapes prepared data")
    return resolved


def _transition_onset_ms(
    suite_path: Path,
    case: DatasetBenchmarkCase,
    *,
    expected_sha256: str,
) -> tuple[int | None, _SourceFile]:
    path = _safe_suite_path(suite_path, case.annotation_path)
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError(f"URFD annotation digest mismatch: {case.case_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    frames = payload.get("frames")
    if payload.get("schema_version") != "1.0" or not isinstance(frames, list):
        raise ValueError("URFD annotation sidecar is invalid")
    if payload.get("sequence") != case.video_sequence:
        raise ValueError("URFD annotation sequence differs from benchmark case")
    if payload.get("video_class") != case.video_class:
        raise ValueError("URFD annotation class differs from benchmark case")
    transition_frames = [
        frame
        for frame in frames
        if frame.get("posture_label") == 0
        and isinstance(frame.get("replay_timestamp_ms"), int)
    ]
    if case.video_class == "fall" and not transition_frames:
        raise ValueError("URFD fall case has no falling-transition phase")
    if case.video_class != "fall" and transition_frames:
        raise ValueError("URFD ADL case unexpectedly contains a fall transition")
    onset = min(frame["replay_timestamp_ms"] for frame in transition_frames) if transition_frames else None
    return onset, _SourceFile(path, "urfd_posture_annotation", PrivacyLevel.RAW_SENSITIVE)


def _duration_ms(frames: list[_FallFrame]) -> int:
    ends = [
        frame.event.time_range.end_ms
        for frame in frames
        if frame.event.time_range.end_ms is not None
    ]
    if len(ends) != len(frames) or not ends:
        raise ValueError("fall feature stream lacks bounded frame windows")
    duration = max(ends)
    if duration <= max(frame.value.timestamp_ms for frame in frames):
        raise ValueError("fall feature duration does not cover its final timestamp")
    return duration


def _candidate_feature(
    *,
    run_id: str,
    variant_index: int,
    case_index: int,
    episode_index: int,
    episode: FallEventCandidateEpisode,
    policy: FallEventCandidatePolicy,
    source_feature_ref: str,
) -> FeatureEvent:
    return FeatureEvent(
        feature_id=(
            f"feature_{run_id}_candidate_{variant_index:02d}_"
            f"{case_index:02d}_{episode_index:03d}"
        ),
        observation_id=(
            f"observation_{run_id}_candidate_{variant_index:02d}_{case_index:02d}"
        ),
        feature_type="video.fall_candidate_episode",
        time_range=TimeRange(start_ms=episode.start_ms, end_ms=episode.end_ms),
        value=episode.model_dump(mode="json"),
        extractor_name=FALL_CANDIDATE_EXTRACTOR,
        extractor_version=policy.candidate_event_version,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        source_feature_refs=[source_feature_ref],
        limitations=[
            "not_a_risk_assessment",
            "not_an_alert",
            "public_dataset_e1_only",
            "source_frame_stream_bound_by_digest",
        ],
    )


def _variant_report(
    *,
    variant_id: str,
    urfd: _UrfdSource,
    caucafall: _CaucafallSource,
    policy_sha256: str,
    policy: FallEventCandidatePolicy,
    cases: list[FallCandidateCaseStressEvaluation],
) -> FallCandidateVariantStressReport:
    negatives = [case for case in cases if not case.positive_case]
    delays = [
        case.transition_onset_detection_delay_ms
        for case in cases
        if case.transition_onset_detection_delay_ms is not None
    ]
    negative_exposure_ms = sum(case.duration_ms for case in negatives)
    negative_episode_count = sum(case.episode_count for case in negatives)
    return FallCandidateVariantStressReport(
        variant_id=variant_id,
        source_urfd_run_id=urfd.manifest.run_id,
        source_urfd_manifest_sha256=sha256_file(urfd.manifest_path),
        source_urfd_report_sha256=sha256_file(urfd.report_path),
        source_urfd_features_sha256=sha256_file(urfd.features_path),
        source_caucafall_run_id=caucafall.manifest.run_id,
        model_policy_sha256=urfd.report.model_binding_policy_sha256,
        fall_feature_policy_sha256=policy.input_fall_feature_policy_sha256,
        candidate_generator_policy_sha256=policy_sha256,
        case_count=len(cases),
        urfd_fall_case_count=sum(case.positive_case for case in cases),
        urfd_fall_activated_count=sum(
            case.positive_case and case.activated for case in cases
        ),
        urfd_adl_negative_case_count=sum(
            case.ground_truth_scope == "urfd_adl_video_class_no_fall"
            for case in cases
        ),
        urfd_adl_false_activation_count=sum(
            case.ground_truth_scope == "urfd_adl_video_class_no_fall"
            and case.activated
            for case in cases
        ),
        caucafall_negative_case_count=sum(
            case.ground_truth_scope == "caucafall_action_level_no_fall"
            for case in cases
        ),
        caucafall_false_activation_count=sum(
            case.ground_truth_scope == "caucafall_action_level_no_fall"
            and case.activated
            for case in cases
        ),
        negative_exposure_ms=negative_exposure_ms,
        negative_episode_count=negative_episode_count,
        false_activations_per_hour=(
            round(negative_episode_count * 3_600_000 / negative_exposure_ms, 6)
            if negative_exposure_ms
            else 0.0
        ),
        episode_count=sum(case.episode_count for case in cases),
        transition_trigger_count=sum(
            case.transition_trigger_count for case in cases
        ),
        settled_trigger_count=sum(case.settled_trigger_count for case in cases),
        detection_delay_count=len(delays),
        mean_transition_onset_detection_delay_ms=(
            round(mean(delays), 3) if delays else None
        ),
        median_transition_onset_detection_delay_ms=(
            round(median(delays), 3) if delays else None
        ),
        minimum_transition_onset_detection_delay_ms=min(delays) if delays else None,
        maximum_transition_onset_detection_delay_ms=max(delays) if delays else None,
        cases=cases,
        limitations=[
            "reused_public_data_not_independent_generalization_evidence",
            "urfd_phase_labels_are_coarse_posture_proxies_not_adjudicated_events",
            "caucafall_labels_are_action_level_without_event_timestamps",
            "not_target_population_or_target_c6c_device_evidence",
            "variant_comparison_is_descriptive_and_not_model_selection",
            "candidate_episodes_do_not_emit_risk_assessment_or_alert",
        ],
    )


def run_fall_candidate_public_stress(
    *,
    urfd_run_dirs: Iterable[Path],
    caucafall_run_dir: Path,
    benchmark_cases_path: Path,
    policy_path: Path,
    runs_dir: Path,
    allow_dirty_source: bool = False,
) -> tuple[RunArtifacts, FallCandidatePublicStressReport]:
    policy_path = Path(policy_path).resolve()
    benchmark_cases_path = Path(benchmark_cases_path).resolve()
    policy = load_fall_candidate_policy(policy_path)
    policy_digest = sha256_file(policy_path)
    urfd_paths = [Path(path).resolve() for path in urfd_run_dirs]
    if len(urfd_paths) != len(KNOWN_VARIANTS) or len(set(urfd_paths)) != len(urfd_paths):
        raise ValueError("candidate stress requires three unique URFD source runs")

    urfd_sources = [
        _load_urfd_source(
            path,
            policy=policy,
            allow_dirty_source=allow_dirty_source,
        )
        for path in urfd_paths
    ]
    urfd_by_variant = {source.report.variant_id: source for source in urfd_sources}
    if set(urfd_by_variant) != set(KNOWN_VARIANTS):
        raise ValueError("URFD sources must contain the frozen three pose variants")
    caucafall = _load_caucafall_source(
        caucafall_run_dir,
        policy=policy,
        allow_dirty_source=allow_dirty_source,
    )
    if [variant.variant_id for variant in caucafall.report.variants] != list(KNOWN_VARIANTS):
        raise ValueError("CAUCAFall source must preserve the frozen variant order")
    for variant_id, source in urfd_by_variant.items():
        caucafall_policy_digest = caucafall.report.pose_model_policy_sha256s.get(
            variant_id,
            caucafall.report.model_binding_policy_sha256,
        )
        if source.report.model_binding_policy_sha256 != caucafall_policy_digest:
            raise ValueError(
                f"pose model policy digest differs across sources: {variant_id}"
            )

    suite, benchmark_cases = load_benchmark_cases(benchmark_cases_path)
    if len(benchmark_cases) != 6:
        raise ValueError("candidate stress requires the frozen six URFD cases")
    if sum(case.video_class == "fall" for case in benchmark_cases) != 3:
        raise ValueError("candidate stress requires three URFD fall cases")
    if sum(case.video_class == "adl" for case in benchmark_cases) != 3:
        raise ValueError("candidate stress requires three URFD ADL cases")
    if any(case.video_dataset != "urfd" for case in benchmark_cases):
        raise ValueError("candidate stress benchmark videos must all be URFD")
    if suite.get("dataset_licenses", {}).get("urfd") != "CC-BY-NC-SA-4.0":
        raise ValueError("candidate stress requires the frozen URFD license")
    benchmark_digest = sha256_file(benchmark_cases_path)
    expected_case_ids = [case.case_id for case in benchmark_cases]
    for source in urfd_sources:
        if source.report.benchmark_cases_sha256 != benchmark_digest:
            raise ValueError("URFD source benchmark digest differs from current suite")
        if [case.case_id for case in source.report.cases] != expected_case_ids:
            raise ValueError("URFD source case order differs from current suite")
        for source_case, benchmark_case in zip(
            source.report.cases, benchmark_cases, strict=True
        ):
            if (
                source_case.video_sequence != benchmark_case.video_sequence
                or source_case.video_class != benchmark_case.video_class
            ):
                raise ValueError("URFD source case metadata differs from suite")

    source_summaries = {
        variant_id: {
            "run_id": source.manifest.run_id,
            "manifest_sha256": sha256_file(source.manifest_path),
            "report_sha256": sha256_file(source.report_path),
            "features_sha256": sha256_file(source.features_path),
        }
        for variant_id, source in sorted(urfd_by_variant.items())
    }
    configuration = {
        "command": "benchmark-fall-candidates",
        "benchmark_id": "v1-g4-public-fall-candidate-stress",
        "benchmark_cases_sha256": benchmark_digest,
        "candidate_policy_id": policy.policy_id,
        "candidate_generator_policy_sha256": policy_digest,
        "fall_feature_policy_sha256": policy.input_fall_feature_policy_sha256,
        "urfd_sources": source_summaries,
        "caucafall_source": {
            "run_id": caucafall.manifest.run_id,
            "manifest_sha256": sha256_file(caucafall.manifest_path),
            "report_sha256": sha256_file(caucafall.report_path),
        },
        "allow_dirty_source": allow_dirty_source,
        "risk_assessment_emitted": False,
        "alert_emitted": False,
    }

    run = RunArtifacts(
        runs_dir=Path(runs_dir),
        stage="v1-g4-fall-event-candidate-public-stress",
        evidence_level=EvidenceLevel.E1,
        configuration=configuration,
    )
    annotation_assets: list[_SourceFile] = []
    variant_reports: list[FallCandidateVariantStressReport] = []
    with run:
        with run.step("record-fall-candidate-source-assets") as step:
            source_files = [
                _SourceFile(policy_path, "fall_candidate_policy", PrivacyLevel.AGGREGATE),
                _SourceFile(benchmark_cases_path, "urfd_benchmark_cases", PrivacyLevel.AGGREGATE),
                *[item for source in urfd_sources for item in source.source_files],
                *caucafall.source_files,
            ]
            recorded: set[str] = set()
            for source_file in source_files:
                asset = _source_asset(source_file)
                if asset.asset_id not in recorded:
                    run.record_asset(asset)
                    recorded.add(asset.asset_id)
            step.outputs.append("source_assets.jsonl")

        generated_urfd: dict[tuple[str, str], tuple[int, list[FallEventCandidateEpisode]]] = {}
        generated_caucafall: dict[
            tuple[str, str], tuple[int, list[FallEventCandidateEpisode]]
        ] = {}
        with run.step("generate-fall-candidate-episodes") as step:
            for variant_index, variant_id in enumerate(KNOWN_VARIANTS):
                source = urfd_by_variant[variant_id]
                for case_index, case in enumerate(benchmark_cases):
                    frames = source.frames_by_case[case.case_id]
                    duration = _duration_ms(frames)
                    episodes = generate_fall_candidate_episodes(
                        [frame.value for frame in frames],
                        duration_ms=duration,
                        case_ref=f"{variant_id}:urfd:{case.case_id}",
                        policy=policy,
                    )
                    generated_urfd[(variant_id, case.case_id)] = (duration, episodes)
                    for episode_index, episode in enumerate(episodes):
                        run.record_feature(
                            _candidate_feature(
                                run_id=run.run_id,
                                variant_index=variant_index,
                                case_index=case_index,
                                episode_index=episode_index,
                                episode=episode,
                                policy=policy,
                                source_feature_ref=next(
                                    frame.event.feature_id
                                    for frame in frames
                                    if frame.value.timestamp_ms
                                    == episode.detected_at_ms
                                ),
                            )
                        )
                caucafall_variant = next(
                    item
                    for item in caucafall.report.variants
                    if item.variant_id == variant_id
                )
                for offset, case in enumerate(caucafall_variant.cases):
                    frames = caucafall.frames_by_variant_case[
                        (variant_id, case.case_id)
                    ]
                    duration = _duration_ms(frames)
                    if duration != case.evaluated_media_duration_ms:
                        raise ValueError("CAUCAFall feature duration differs from report")
                    episodes = generate_fall_candidate_episodes(
                        [frame.value for frame in frames],
                        duration_ms=duration,
                        case_ref=f"{variant_id}:caucafall:{case.case_id}",
                        policy=policy,
                    )
                    generated_caucafall[(variant_id, case.case_id)] = (
                        duration,
                        episodes,
                    )
                    for episode_index, episode in enumerate(episodes):
                        run.record_feature(
                            _candidate_feature(
                                run_id=run.run_id,
                                variant_index=variant_index,
                                case_index=len(benchmark_cases) + offset,
                                episode_index=episode_index,
                                episode=episode,
                                policy=policy,
                                source_feature_ref=next(
                                    frame.event.feature_id
                                    for frame in frames
                                    if frame.value.timestamp_ms
                                    == episode.detected_at_ms
                                ),
                            )
                        )
            if (run.run_dir / "features.jsonl").is_file():
                step.outputs.append("features.jsonl")

        with run.step("evaluate-public-candidate-stress") as step:
            annotation_onsets: dict[str, int | None] = {}
            first_source = urfd_by_variant[KNOWN_VARIANTS[0]]
            first_report_cases = {case.case_id: case for case in first_source.report.cases}
            for case in benchmark_cases:
                onset, annotation_asset = _transition_onset_ms(
                    benchmark_cases_path,
                    case,
                    expected_sha256=first_report_cases[case.case_id].annotation_sha256,
                )
                annotation_onsets[case.case_id] = onset
                annotation_assets.append(annotation_asset)
                expected_digest = first_report_cases[case.case_id].annotation_sha256
                if any(
                    next(
                        item.annotation_sha256
                        for item in source.report.cases
                        if item.case_id == case.case_id
                    )
                    != expected_digest
                    for source in urfd_sources
                ):
                    raise ValueError("URFD annotation digest differs across variants")

            for variant_id in KNOWN_VARIANTS:
                case_results: list[FallCandidateCaseStressEvaluation] = []
                for case in benchmark_cases:
                    duration, episodes = generated_urfd[(variant_id, case.case_id)]
                    positive = case.video_class == "fall"
                    onset = annotation_onsets[case.case_id]
                    delay = (
                        min(episode.detected_at_ms for episode in episodes) - onset
                        if positive and episodes and onset is not None
                        else None
                    )
                    case_results.append(
                        FallCandidateCaseStressEvaluation(
                            case_ref=case.case_id,
                            variant_id=variant_id,
                            dataset_id="urfd",
                            ground_truth_scope=(
                                "urfd_fall_video_class_with_phase_onset_proxy"
                                if positive
                                else "urfd_adl_video_class_no_fall"
                            ),
                            scenario_group=case.video_class,
                            positive_case=positive,
                            duration_ms=duration,
                            input_frame_count=len(
                                urfd_by_variant[variant_id].frames_by_case[case.case_id]
                            ),
                            episode_count=len(episodes),
                            activated=bool(episodes),
                            transition_trigger_count=sum(
                                episode.trigger_path
                                == "rapid_descent_then_horizontal"
                                for episode in episodes
                            ),
                            settled_trigger_count=sum(
                                episode.trigger_path
                                == "settled_horizontal_low_motion"
                                for episode in episodes
                            ),
                            transition_onset_detection_delay_ms=delay,
                            limitations=[
                                "reused_urfd_development_data",
                                "posture_transition_onset_is_not_adjudicated_event_onset",
                                "simulated_public_subject_not_target_population",
                            ],
                        )
                    )
                caucafall_variant = next(
                    item
                    for item in caucafall.report.variants
                    if item.variant_id == variant_id
                )
                for case in caucafall_variant.cases:
                    duration, episodes = generated_caucafall[
                        (variant_id, case.case_id)
                    ]
                    case_results.append(
                        FallCandidateCaseStressEvaluation(
                            case_ref=case.case_id,
                            variant_id=variant_id,
                            dataset_id="caucafall-v4",
                            ground_truth_scope="caucafall_action_level_no_fall",
                            scenario_group=case.activity,
                            positive_case=False,
                            duration_ms=duration,
                            input_frame_count=case.sampled_frames,
                            episode_count=len(episodes),
                            activated=bool(episodes),
                            transition_trigger_count=sum(
                                episode.trigger_path
                                == "rapid_descent_then_horizontal"
                                for episode in episodes
                            ),
                            settled_trigger_count=sum(
                                episode.trigger_path
                                == "settled_horizontal_low_motion"
                                for episode in episodes
                            ),
                            limitations=[
                                "reused_caucafall_development_data",
                                "action_level_no_fall_label_without_event_timestamp",
                                "public_subject_not_target_population_or_device",
                            ],
                        )
                    )
                variant_reports.append(
                    _variant_report(
                        variant_id=variant_id,
                        urfd=urfd_by_variant[variant_id],
                        caucafall=caucafall,
                        policy_sha256=policy_digest,
                        policy=policy,
                        cases=case_results,
                    )
                )
            step.outputs.append("aggregate_candidate_metrics_in_memory")

        with run.step("record-fall-candidate-evaluation-assets") as step:
            recorded = set(run.manifest.inputs)
            for source_file in annotation_assets:
                asset = _source_asset(source_file)
                if asset.asset_id not in recorded:
                    run.record_asset(asset)
                    recorded.add(asset.asset_id)
            step.outputs.append("source_assets.jsonl")

        report = FallCandidatePublicStressReport(
            benchmark_id="v1-g4-public-fall-candidate-stress",
            benchmark_version=FALL_CANDIDATE_BENCHMARK_VERSION,
            evidence_level=EvidenceLevel.E1,
            candidate_policy_id=policy.policy_id,
            candidate_generator_policy_sha256=policy_digest,
            fall_feature_policy_sha256=policy.input_fall_feature_policy_sha256,
            urfd_benchmark_id=suite["benchmark_id"],
            urfd_benchmark_cases_sha256=benchmark_digest,
            caucafall_suite_id=caucafall.report.suite_id,
            caucafall_suite_manifest_sha256=caucafall.report.suite_manifest_sha256,
            source_caucafall_run_id=caucafall.manifest.run_id,
            source_caucafall_manifest_sha256=sha256_file(caucafall.manifest_path),
            source_caucafall_report_sha256=sha256_file(caucafall.report_path),
            variant_count=len(variant_reports),
            case_evaluation_count=sum(
                variant.case_count for variant in variant_reports
            ),
            variants=variant_reports,
            limitations=[
                *policy.limitations,
                "public_data_were_used_during_v1_development_and_are_not_held_out",
                "results_do_not_estimate_target_device_accuracy_or_generalization",
                "urfd_positive_scope_is_video_class_plus_coarse_phase_onset_only",
                "caucafall_negative_scope_is_action_level_only",
                "three_pose_variants_have_different_tracking_and_license_constraints",
                "candidate_output_is_tooling_only_not_risk_assessment_or_alert",
            ],
        )
        with run.step("write-fall-candidate-public-stress-report") as step:
            report_path = run.write_report(
                "fall-candidate-public-stress-report.json",
                report,
            )
            step.outputs.append(run.relative(report_path))
    return run, report
