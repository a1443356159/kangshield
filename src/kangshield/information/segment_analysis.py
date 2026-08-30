"""Turn selected in-memory pose and speech features into product-level facts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from .contracts import (
    DomainCandidate,
    FeatureEvent,
    PrivacyLevel,
    RiskDomain,
    TimeRange,
)
from .longitudinal.store import LongitudinalStore, dumps_compact
from .multidomain import classify_fraud_text, load_policy
from .pose_backend import PoseDetection
from .speech_backend import tag_transcript


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


def merge_daily_feature(
    store: LongitudinalStore,
    *,
    started: datetime,
    result: AnalysisResult,
    source_ref: str,
    now: datetime,
    policy: dict[str, Any],
) -> None:
    """Merge one audited daytime segment into the person's daily summary."""

    local_hour = started.astimezone().hour
    mental_policy = policy["mental_wellbeing"]
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
    if source_ref in existing_refs:
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
            "source_refs_json": dumps_compact([*existing_refs, source_ref]),
            "updated_at": now.isoformat(),
        }
    )


class SegmentResultSummarizer:
    """Apply fall and language rules to selected feature events."""

    def __init__(self, policy_path: Path) -> None:
        self.policy, _ = load_policy(policy_path)

    def summarize(
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
    ) -> AnalysisResult:
        pose = [item for item in features if item["feature_type"] == "video.pose_frame"]
        qualified_pose = [
            item
            for item in pose
            if item.get("quality") is not None and float(item["quality"]) >= 0.5
        ]
        result = AnalysisResult(
            pose_quality_seconds=min(duration_ms / 1000, len(qualified_pose) / 5.0),
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
            speech_interaction=(
                speech_segment_count / max(duration_ms / 60000, 1 / 60)
            ),
        )
        result.candidates.extend(
            self._fall_candidates(
                pose,
                duration_ms=duration_ms,
                frame_width=frame_width,
                frame_height=frame_height,
                capture_started_at=capture_started_at,
                media_digest=media_digest,
            )
        )
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
            transcript_excerpt = _source_transcript_excerpt(item, transcripts)
            for tag, category in (
                ("help_request", "help_speech"),
                ("fall_related", "fall_speech"),
            ):
                if tag not in tags:
                    continue
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
                        {
                            "tag": tag,
                            **(
                                {"transcript_excerpt": transcript_excerpt}
                                if transcript_excerpt
                                else {}
                            ),
                        },
                    )
                )
        for item in transcripts.values():
            text = str(item.get("value", {}).get("text", ""))
            categories, hard_negative = classify_fraud_text(text, self.policy)
            if not categories or hard_negative:
                continue
            result.candidates.append(
                (
                    _candidate(
                        RiskDomain.FRAUD,
                        "fraud_language",
                        _event_at(capture_started_at, item),
                        media_digest,
                        item["feature_id"],
                        [f"matched_context:{category}" for category in categories],
                    ),
                    {
                        "categories": categories,
                        "transcript_excerpt": _short_transcript(text),
                    },
                )
            )
        return result

    @staticmethod
    def _fall_candidates(
        pose_features: list[dict[str, Any]],
        *,
        duration_ms: int,
        frame_width: int,
        frame_height: int,
        capture_started_at: datetime,
        media_digest: str,
    ) -> list[tuple[DomainCandidate, dict[str, Any]]]:
        if not pose_features:
            return []
        from .fall_candidates import (
            generate_fall_candidate_episodes,
            load_fall_candidate_policy,
        )
        from .fall_features import FallMotionFeatureExtractor, load_fall_feature_config

        from .resources import policy_path

        feature_config = load_fall_feature_config(
            policy_path("v1-g4-fall-features.json")
        )
        candidate_policy = load_fall_candidate_policy(
            policy_path("v1-g4-event-candidate-policy.json")
        )
        extractor = FallMotionFeatureExtractor(
            feature_config, frame_width=frame_width, frame_height=frame_height
        )
        values = []
        for raw in pose_features:
            source = FeatureEvent.model_validate(raw)
            values.append(extractor.process(source))
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
        return candidates


def pose_feature(
    *,
    run_id: str,
    sequence: int,
    timestamp_ms: int,
    sample_fps: float,
    observation_id: str,
    detections: list[PoseDetection],
    model_digest: str | None,
    extractor_version: str | None,
) -> FeatureEvent:
    confidences = [
        item.confidence for item in detections if item.confidence is not None
    ]
    point_confidences = [
        point[2]
        for detection in detections
        for point in detection.keypoints_xyc
        if len(point) >= 3
    ]
    visible_ratio = (
        sum(value >= 0.5 for value in point_confidences) / len(point_confidences)
        if point_confidences
        else None
    )
    end_ms = timestamp_ms + max(1, round(1000.0 / sample_fps))
    return FeatureEvent(
        feature_id=f"feature_{run_id}_pose_{sequence:06d}",
        observation_id=observation_id,
        feature_type="video.pose_frame",
        time_range=TimeRange(start_ms=timestamp_ms, end_ms=end_ms),
        value={
            "frame_sequence": sequence,
            "person_count": len(detections),
            "detections": [
                {
                    "bbox_xyxy": item.bbox_xyxy,
                    "keypoints_xyc": item.keypoints_xyc,
                    "confidence": item.confidence,
                    "track_id": item.track_id,
                }
                for item in detections
            ],
        },
        confidence=round(mean(confidences), 6) if confidences else None,
        quality=round(visible_ratio, 6) if visible_ratio is not None else None,
        extractor_name="ultralytics-pose-adapter",
        extractor_version=extractor_version or "unknown",
        model_digest=model_digest,
        privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
        limitations=["uncalibrated_image_coordinates", "coco_17_keypoints"],
    )


def speech_features(
    *,
    run_id: str,
    observation_id: str,
    segments: list[Any],
    bindings: list[Any],
    timeline_offset_ms: int = 0,
) -> tuple[list[FeatureEvent], list[FeatureEvent], list[FeatureEvent]]:
    if timeline_offset_ms < 0:
        raise ValueError("timeline_offset_ms must be non-negative")
    speech_events: list[FeatureEvent] = []
    transcript_events: list[FeatureEvent] = []
    semantic_events: list[FeatureEvent] = []
    vad_binding = _binding_for_task(bindings, "voice_activity_detection")
    asr_binding = _binding_for_task(bindings, "mandarin_speech_recognition")
    for sequence, segment in enumerate(segments):
        time_range = TimeRange(
            start_ms=timeline_offset_ms + segment.start_ms,
            end_ms=timeline_offset_ms + segment.end_ms,
        )
        speech_id = f"feature_{run_id}_speech_{sequence:04d}"
        transcript_id = f"feature_{run_id}_transcript_{sequence:04d}"
        speech_events.append(
            FeatureEvent(
                feature_id=speech_id,
                observation_id=observation_id,
                feature_type="audio.speech_segment",
                time_range=time_range,
                value={"speech_detected": True},
                confidence=segment.confidence,
                extractor_name="funasr-vad-adapter",
                extractor_version=_backend_version(vad_binding),
                model_digest=vad_binding.model_digest if vad_binding else None,
                privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
            )
        )
        transcript_events.append(
            FeatureEvent(
                feature_id=transcript_id,
                observation_id=observation_id,
                feature_type="language.transcript_segment",
                time_range=time_range,
                value={"text": segment.text, "language": segment.language},
                confidence=segment.confidence,
                extractor_name="funasr-asr-adapter",
                extractor_version=_backend_version(asr_binding),
                model_digest=asr_binding.model_digest if asr_binding else None,
                privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                source_feature_refs=[speech_id],
                limitations=["automatic_transcript_requires_human_review"],
            )
        )
        tags = tag_transcript(segment.text)
        if tags:
            semantic_events.append(
                FeatureEvent(
                    feature_id=f"feature_{run_id}_semantic_{sequence:04d}",
                    observation_id=observation_id,
                    feature_type="language.lexical_tags",
                    time_range=time_range,
                    value={"tags": tags},
                    extractor_name="kangshield-keyword-rules",
                    extractor_version="0.1.0",
                    privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                    source_feature_refs=[transcript_id],
                    limitations=[
                        "keyword_match_is_not_intent_or_risk_classification"
                    ],
                )
            )
    return speech_events, transcript_events, semantic_events


def _binding_for_task(bindings: list[Any], task: str) -> Any | None:
    return next((binding for binding in bindings if binding.task == task), None)


def _backend_version(binding: Any | None) -> str:
    if binding is None:
        return "unknown"
    configured = binding.configuration.get("funasr_version")
    return str(configured or binding.model_version or "unknown")


def _source_transcript_excerpt(
    feature: dict[str, Any], transcripts: dict[str, dict[str, Any]]
) -> str | None:
    for feature_ref in feature.get("source_feature_refs", []):
        source = transcripts.get(str(feature_ref))
        if source is None:
            continue
        excerpt = _short_transcript(str(source.get("value", {}).get("text", "")))
        if excerpt:
            return excerpt
    return None


def _short_transcript(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(text.split()).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


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
