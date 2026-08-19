"""Idempotent scanner from bounded capture runs into the multidomain store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .artifacts import RunArtifacts
from .contracts import (
    DomainCandidate,
    EvidenceLevel,
    FeatureEvent,
    PrivacyLevel,
    RiskDomain,
    SourceType,
)
from .longitudinal.store import LongitudinalStore, dumps_compact
from .multidomain import classify_fraud_text, insert_candidate, load_policy
from .privacy import sha256_file

ANALYZER_VERSION = "multidomain-incremental-v0.1.0"


@dataclass
class AnalysisResult:
    pose_quality_seconds: float = 0
    audio_valid_seconds: float = 0
    candidates: list[tuple[DomainCandidate, dict[str, Any]]] = field(
        default_factory=list
    )
    eligible_segments: int = 0
    daytime_presence: float | None = None
    activity_level: float | None = None
    speech_interaction: float | None = None


class DefaultMediaAnalyzer:
    """Single-worker analyzer that retains successfully loaded models."""

    def __init__(self, analysis_runs_dir: Path, policy_path: Path) -> None:
        self.analysis_runs_dir = Path(analysis_runs_dir)
        self.policy, _ = load_policy(policy_path)
        self._pose_backend: Any = None
        self._speech_backend: Any = None

    def _ensure_models(self) -> None:
        if self._pose_backend is not None and self._speech_backend is not None:
            return
        model = Path("models/yolo26n-pose.pt")
        if not model.is_file():
            raise RuntimeError("pose_model_unavailable")
        from .pose_backend import UltralyticsPoseBackend
        from .speech_backend import FunASRSpeechBackend

        self._pose_backend = UltralyticsPoseBackend(
            model=model,
            device="auto",
            image_size=640,
            confidence=0.35,
            track=True,
        )
        self._speech_backend = FunASRSpeechBackend(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            device="auto",
            language="zh",
            offline=True,
        )

    def __call__(
        self,
        media_path: Path,
        *,
        device_ref: str,
        elder_ref: str,
        capture_started_at: datetime,
        media_digest: str,
    ) -> AnalysisResult:
        self._ensure_models()
        from .multimodal_pipeline import MultimodalPipelineConfig, run_multimodal_pipeline

        with RunArtifacts(
            self.analysis_runs_dir,
            stage="v2-multidomain-incremental-analysis",
            evidence_level=EvidenceLevel.E2,
            configuration={
                "analyzer_version": ANALYZER_VERSION,
                "device_ref": device_ref,
                "elder_ref": elder_ref,
                "source_media_digest": media_digest,
                "transcripts_persisted_to_longitudinal_db": False,
            },
        ) as run:
            report = run_multimodal_pipeline(
                video_path=media_path,
                audio_path=media_path,
                pose_backend=self._pose_backend,
                speech_backend=self._speech_backend,
                run=run,
                config=MultimodalPipelineConfig(
                    video_sample_fps=5.0,
                    fusion_window_ms=2000,
                    max_duration_s=None,
                ),
                evidence_level=EvidenceLevel.E2,
                source_type=SourceType.LOCAL_FILE,
                device_ref=device_ref,
                elder_ref=elder_ref,
            )
            features_path = run.run_dir / "features.jsonl"
            features = [
                json.loads(line)
                for line in features_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            probe = json.loads(
                (run.reports_dir / "multimodal-container-probe.json").read_text(
                    encoding="utf-8"
                )
            )
            result, fall_events = self._summarize(
                features,
                duration_ms=report.duration_ms,
                sampled_video_frames=report.sampled_video_frames,
                pose_frames_with_people=report.pose_frames_with_people,
                speech_segment_count=report.speech_segment_count,
                capture_started_at=capture_started_at,
                media_digest=media_digest,
                frame_width=int(probe["technical_metadata"]["width"]),
                frame_height=int(probe["technical_metadata"]["height"]),
            )
            for event in fall_events:
                run.record_feature(event)
                run.record_feature_artifact(
                    "artifacts/fall-motion-features.jsonl", event
                )
        return result

    def _summarize(
        self,
        features: list[dict[str, Any]],
        *,
        duration_ms: int,
        sampled_video_frames: int,
        pose_frames_with_people: int,
        speech_segment_count: int,
        capture_started_at: datetime,
        media_digest: str,
        frame_width: int,
        frame_height: int,
    ) -> tuple[AnalysisResult, list[FeatureEvent]]:
        pose = [item for item in features if item["feature_type"] == "video.pose_frame"]
        qualified_pose = [
            item
            for item in pose
            if item.get("quality") is not None and float(item["quality"]) >= 0.5
        ]
        result = AnalysisResult(
            pose_quality_seconds=min(
                duration_ms / 1000, len(qualified_pose) / 5.0
            ),
            audio_valid_seconds=duration_ms / 1000,
            eligible_segments=1 if qualified_pose or speech_segment_count else 0,
            daytime_presence=(
                pose_frames_with_people / sampled_video_frames
                if sampled_video_frames
                else None
            ),
            activity_level=(
                len(qualified_pose) / sampled_video_frames
                if sampled_video_frames
                else None
            ),
            speech_interaction=(speech_segment_count / max(duration_ms / 60000, 1 / 60)),
        )
        fall_candidates, fall_events = self._fall_candidates(
            pose,
            duration_ms=duration_ms,
            frame_width=frame_width,
            frame_height=frame_height,
            capture_started_at=capture_started_at,
            media_digest=media_digest,
        )
        result.candidates.extend(fall_candidates)
        transcripts = {
            item["feature_id"]: item
            for item in features
            if item["feature_type"] == "language.transcript_segment"
        }
        semantics = [
            item for item in features if item["feature_type"] == "language.lexical_tags"
        ]
        for item in semantics:
            tags = set(item.get("value", {}).get("tags", []))
            occurred_at = _event_at(capture_started_at, item)
            for tag, category in (
                ("help_request", "help_speech"),
                ("fall_related", "fall_speech"),
            ):
                if tag in tags:
                    result.candidates.append(
                        (
                            _candidate(
                                RiskDomain.FALL,
                                category,
                                occurred_at,
                                media_digest,
                                item["feature_id"],
                                [f"lexical_tag:{tag}"],
                            ),
                            {"tag": tag},
                        )
                    )
        for item in transcripts.values():
            text = str(item.get("value", {}).get("text", ""))
            categories, hard_negative = classify_fraud_text(text, self.policy)
            if not categories or hard_negative:
                continue
            occurred_at = _event_at(capture_started_at, item)
            result.candidates.append(
                (
                    _candidate(
                        RiskDomain.FRAUD,
                        "fraud_language",
                        occurred_at,
                        media_digest,
                        item["feature_id"],
                        [f"matched_context:{category}" for category in categories],
                    ),
                    {"categories": categories},
                )
            )
        return result, fall_events

    def _fall_candidates(
        self,
        pose_features: list[dict[str, Any]],
        *,
        duration_ms: int,
        frame_width: int,
        frame_height: int,
        capture_started_at: datetime,
        media_digest: str,
    ) -> tuple[list[tuple[DomainCandidate, dict[str, Any]]], list[FeatureEvent]]:
        if not pose_features:
            return [], []
        from .fall_candidates import (
            generate_fall_candidate_episodes,
            load_fall_candidate_policy,
        )
        from .fall_features import FallMotionFeatureExtractor, load_fall_feature_config

        feature_config = load_fall_feature_config(
            Path("configs/v1-g4-fall-features.json")
        )
        candidate_policy = load_fall_candidate_policy(
            Path("configs/v1-g4-event-candidate-policy.json")
        )
        extractor = FallMotionFeatureExtractor(
            feature_config, frame_width=frame_width, frame_height=frame_height
        )
        values = []
        events: list[FeatureEvent] = []
        for raw in pose_features:
            source = FeatureEvent.model_validate(raw)
            value = extractor.process(source)
            values.append(value)
            events.append(
                FeatureEvent(
                    feature_id=f"{source.feature_id}_fall_motion",
                    observation_id=source.observation_id,
                    feature_type="video.fall_motion_frame",
                    time_range=source.time_range,
                    value=value.model_dump(mode="json"),
                    extractor_name="kangshield-fall-motion-features",
                    extractor_version=feature_config.feature_version,
                    privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                    source_feature_refs=[source.feature_id],
                    limitations=[
                        "candidate_policy_is_pilot_unvalidated_on_target_device"
                    ],
                )
            )
        episodes = generate_fall_candidate_episodes(
            values,
            duration_ms=max(duration_ms, values[-1].timestamp_ms + 1),
            case_ref=f"sha256:{media_digest}",
            policy=candidate_policy,
        )
        candidates = []
        for episode in episodes:
            occurred_at = capture_started_at + timedelta(
                milliseconds=episode.detected_at_ms
            )
            candidates.append(
                (
                    _candidate(
                        RiskDomain.FALL,
                        "fall_candidate",
                        occurred_at,
                        media_digest,
                        episode.candidate_id,
                        [f"trigger_path:{episode.trigger_path}"],
                    ),
                    {
                        "start_ms": episode.start_ms,
                        "detected_at_ms": episode.detected_at_ms,
                        "end_ms": episode.end_ms,
                        "trigger_path": episode.trigger_path,
                        "candidate_version": episode.candidate_version,
                    },
                )
            )
        return candidates, events


class IncrementalAnalyzer:
    def __init__(
        self,
        *,
        elder_ref: str,
        device_ref: str,
        store_root: Path,
        runs_dir: Path,
        policy_path: Path,
        media_analyzer: Callable[..., AnalysisResult] | None = None,
    ) -> None:
        self.elder_ref = elder_ref
        self.device_ref = device_ref
        self.store_root = Path(store_root)
        self.runs_dir = Path(runs_dir)
        self.policy_path = Path(policy_path)
        self.policy, _ = load_policy(self.policy_path)
        self.lookback_days = int(self.policy["initial_lookback_days"])
        self.media_analyzer = media_analyzer or DefaultMediaAnalyzer(
            self.runs_dir / "product-analysis", self.policy_path
        )

    def scan_once(self, *, now: datetime | None = None) -> dict[str, int]:
        now = _aware(now or datetime.now(timezone.utc))
        counts = {"discovered": 0, "completed": 0, "skipped": 0, "failed": 0}
        with LongitudinalStore(self.elder_ref, root=self.store_root) as store:
            for report_path in sorted(self.runs_dir.glob("*/reports/stream-capture.json")):
                counts["discovered"] += 1
                try:
                    outcome = self._process_report(report_path, store=store, now=now)
                except Exception as error:
                    counts["failed"] += 1
                    self._record_unresolved_failure(
                        report_path, store=store, now=now, error=error
                    )
                else:
                    counts[outcome] += 1
        return counts

    def _process_report(
        self, report_path: Path, *, store: LongitudinalStore, now: datetime
    ) -> str:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        observation = payload.get("media_probe", {}).get("observation", {})
        if observation.get("device_ref") != self.device_ref:
            return "skipped"
        if not payload.get("capture_artifact_ready") or not payload.get(
            "same_container_multimodal_ready"
        ):
            return "skipped"
        run_dir = report_path.parent.parent
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            return "skipped"
        started = _parse_time(
            payload.get("capture_started_at") or manifest.get("started_at")
        )
        ended = _parse_time(
            payload.get("capture_ended_at")
            or manifest.get("finished_at")
            or manifest.get("started_at")
        )
        if ended < now - timedelta(days=self.lookback_days):
            return "skipped"
        media_path = _safe_artifact(run_dir, str(payload["output_artifact"]))
        media_digest = sha256_file(media_path)
        if store.analysis_status(media_digest) == "completed":
            return "skipped"
        report_digest = sha256_file(report_path)
        result = self.media_analyzer(
            media_path,
            device_ref=self.device_ref,
            elder_ref=self.elder_ref,
            capture_started_at=started,
            media_digest=media_digest,
        )
        for candidate, candidate_payload in result.candidates:
            insert_candidate(
                store,
                candidate,
                device_ref=self.device_ref,
                payload=candidate_payload,
            )
        self._merge_daily_feature(store, started, result, media_digest, now)
        store.record_analysis_attempt(
            media_digest=media_digest,
            report_digest=report_digest,
            run_id=str(manifest["run_id"]),
            device_ref=self.device_ref,
            attempted_at=now.isoformat(),
            captured_start_at=started.isoformat(),
            captured_end_at=ended.isoformat(),
            status="completed",
            pose_quality_seconds=result.pose_quality_seconds,
            audio_valid_seconds=result.audio_valid_seconds,
        )
        return "completed"

    def _merge_daily_feature(
        self,
        store: LongitudinalStore,
        started: datetime,
        result: AnalysisResult,
        media_digest: str,
        now: datetime,
    ) -> None:
        local_hour = started.astimezone().hour
        mental_policy = self.policy["mental_wellbeing"]
        if not (
            int(mental_policy["daytime_start_hour"])
            <= local_hour
            < int(mental_policy["daytime_end_hour"])
        ):
            return
        local_day = started.astimezone().date().isoformat()
        existing = store._connection.execute(
            "SELECT * FROM daily_features WHERE local_date = ?", (local_day,)
        ).fetchone()
        existing_refs = json.loads(existing["source_refs_json"]) if existing else []
        if media_digest in existing_refs:
            return
        previous_count = int(existing["eligible_segments"]) if existing else 0
        new_count = previous_count + result.eligible_segments

        def merged(name: str, new_value: float | None) -> float | None:
            old = existing[name] if existing else None
            if new_value is None:
                return old
            if old is None or previous_count == 0:
                return new_value
            return (float(old) * previous_count + new_value) / max(new_count, 1)

        refs = [*existing_refs, media_digest]
        store.upsert_daily_feature(
            {
                "local_date": local_day,
                "eligible_segments": new_count,
                "daytime_presence": merged("daytime_presence", result.daytime_presence),
                "activity_level": merged("activity_level", result.activity_level),
                "speech_interaction": merged(
                    "speech_interaction", result.speech_interaction
                ),
                "sleep_regularity": existing["sleep_regularity"] if existing else None,
                "sleep_confirmed": int(existing["sleep_confirmed"]) if existing else 0,
                "source_refs_json": dumps_compact(refs),
                "updated_at": now.isoformat(),
            }
        )

    def _record_unresolved_failure(
        self,
        report_path: Path,
        *,
        store: LongitudinalStore,
        now: datetime,
        error: Exception,
    ) -> None:
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            run_dir = report_path.parent.parent
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            media_path = _safe_artifact(run_dir, str(payload["output_artifact"]))
            media_digest = sha256_file(media_path)
            observation = payload.get("media_probe", {}).get("observation", {})
            if observation.get("device_ref") != self.device_ref:
                return
            started = _parse_time(
                payload.get("capture_started_at") or manifest.get("started_at")
            )
            ended = _parse_time(
                payload.get("capture_ended_at")
                or manifest.get("finished_at")
                or manifest.get("started_at")
            )
            store.record_analysis_attempt(
                media_digest=media_digest,
                report_digest=sha256_file(report_path),
                run_id=str(manifest.get("run_id", run_dir.name)),
                device_ref=self.device_ref,
                attempted_at=now.isoformat(),
                captured_start_at=started.isoformat(),
                captured_end_at=ended.isoformat(),
                status="failed",
                error=type(error).__name__,
            )
        except Exception:
            return


def _candidate(
    domain: RiskDomain,
    category: str,
    occurred_at: datetime,
    media_digest: str,
    feature_id: str,
    summaries: list[str],
) -> DomainCandidate:
    digest = hashlib.sha256(
        f"{domain.value}|{category}|{media_digest}|{feature_id}".encode()
    ).hexdigest()[:24]
    return DomainCandidate(
        candidate_id=f"candidate_{digest}",
        domain=domain,
        category=category,
        occurred_at=occurred_at,
        evidence_refs=[f"sha256:{media_digest}", feature_id],
        evidence_summary=summaries,
    )


def _event_at(started: datetime, feature: dict[str, Any]) -> datetime:
    start_ms = int(feature.get("time_range", {}).get("start_ms") or 0)
    return started + timedelta(milliseconds=start_ms)


def _safe_artifact(run_dir: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or not pure.parts
        or pure.parts[0] != "artifacts"
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in relative
    ):
        raise ValueError("invalid capture artifact path")
    path = run_dir.joinpath(*pure.parts).resolve()
    root = run_dir.resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("capture artifact is outside its run or missing")
    return path


def _parse_time(value: str | None) -> datetime:
    if not value:
        raise ValueError("capture wall time is missing")
    return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
