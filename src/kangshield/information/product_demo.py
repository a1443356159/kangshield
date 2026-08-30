"""Synthetic, privacy-safe records and media for the local demonstration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .longitudinal.store import DEFAULT_STORE_ROOT, LongitudinalStore
from .multidomain import build_snapshot, load_policy
from .resources import policy_path as bundled_policy_path


def seed_product_demo(
    *,
    elder_ref: str,
    device_ref: str,
    store_root: Path = DEFAULT_STORE_ROOT,
    policy_path: Path = bundled_policy_path("v2-multidomain-risk-policy.json"),
    edge_policy_path: Path = bundled_policy_path("v2-edge-segment-policy.json"),
    now: datetime | None = None,
) -> dict[str, int]:
    """Seed an idempotent demo without real-person, device, or raw-stream data."""

    if not elder_ref.startswith("demo-") or not device_ref.startswith("demo-"):
        raise ValueError("demo mode requires demo-* elder and device references")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_day = now.astimezone().date()
    bucket = now.strftime("%Y%m%d%H")
    created = {
        "captures": 0,
        "daily_features": 0,
        "candidates": 0,
        "archives": 0,
        "history": 0,
    }
    policy, digest = load_policy(policy_path)

    with LongitudinalStore(elder_ref, root=store_root) as store:
        media_digest = _digest(f"kangshield-demo-capture-{device_ref}-{bucket}")
        if store.analysis_status(media_digest) is None:
            created["captures"] += 1
        store.record_analysis_attempt(
            media_digest=media_digest,
            report_digest=_digest(f"kangshield-demo-report-{bucket}"),
            run_id=f"demo-run-{bucket}",
            device_ref=device_ref,
            attempted_at=now.isoformat(),
            captured_start_at=(now - timedelta(minutes=14)).isoformat(),
            captured_end_at=(now - timedelta(minutes=2)).isoformat(),
            status="completed",
            pose_quality_seconds=720,
            audio_valid_seconds=720,
        )

        baseline = [
            (0.74, 0.58, 0.43, 0.81),
            (0.75, 0.60, 0.45, 0.82),
            (0.76, 0.62, 0.47, 0.83),
            (0.74, 0.59, 0.44, 0.81),
            (0.75, 0.61, 0.46, 0.82),
            (0.77, 0.60, 0.45, 0.84),
            (0.73, 0.58, 0.43, 0.80),
            (0.76, 0.62, 0.47, 0.83),
            (0.74, 0.59, 0.44, 0.81),
            (0.75, 0.61, 0.46, 0.82),
        ]
        for offset, values in zip(range(10, 0, -1), baseline, strict=True):
            day = local_day - timedelta(days=offset)
            store.upsert_daily_feature(_daily_row(day.isoformat(), values, now))
            created["daily_features"] += 1
        # One clear daytime-presence deviation produces a level-2 wellbeing result.
        store.upsert_daily_feature(
            _daily_row(local_day.isoformat(), (0.70, 0.60, 0.45, 0.82), now)
        )
        created["daily_features"] += 1

        candidates = [
            _candidate(
                candidate_id=f"demo-fall-{local_day.isoformat()}",
                device_ref=device_ref,
                domain="fall",
                category="fall_candidate",
                occurred_at=now - timedelta(minutes=42),
                summary="客厅区域出现快速下移并持续低位姿态，等待人工核实",
                payload={"demo": True},
                quality=0.86,
            ),
            _candidate(
                candidate_id=f"demo-fraud-transfer-{local_day.isoformat()}",
                device_ref=device_ref,
                domain="fraud",
                category="transfer_investment",
                occurred_at=now - timedelta(minutes=18, seconds=20),
                summary="环境对话出现转账至安全账户的可疑上下文",
                payload={
                    "demo": True,
                    "categories": ["transfer_investment"],
                    "transcript_excerpt": "请立即把钱转到安全账户，我来帮您处理。",
                },
                quality=0.91,
            ),
            _candidate(
                candidate_id=f"demo-fraud-urgent-{local_day.isoformat()}",
                device_ref=device_ref,
                domain="fraud",
                category="urgency_secrecy",
                occurred_at=now - timedelta(minutes=18),
                summary="同一对话要求立即处理并对家人保密",
                payload={
                    "demo": True,
                    "categories": ["urgency_secrecy"],
                    "transcript_excerpt": "这件事要保密，不要告诉家人，马上处理。",
                },
                quality=0.89,
            ),
        ]
        for candidate in candidates:
            if store.upsert_domain_candidate(candidate):
                created["candidates"] += 1
            else:
                # Refresh presentation-only payload when the demo evolves on the same day.
                with store._connection:
                    store._connection.execute(
                        "UPDATE domain_candidates SET evidence_summary_json = ?,"
                        " payload_json = ?, quality = ? WHERE candidate_id = ?",
                        (
                            candidate["evidence_summary_json"],
                            candidate["payload_json"],
                            candidate["quality"],
                            candidate["candidate_id"],
                        ),
                    )

        created["archives"] = _seed_demo_archives(
            store,
            device_ref=device_ref,
            edge_policy_path=edge_policy_path,
        )

        history_count = int(
            store._connection.execute(
                "SELECT COUNT(*) FROM domain_assessments"
            ).fetchone()[0]
        )
        if history_count == 0:
            samples = {
                "fall": [0, 0, 1, 0, 1, 1, 2, 1, 2],
                "mental_wellbeing": [0, 0, 0, 1, 1, 1, 2, 1, 2],
                "fraud": [0, 0, 0, 0, 1, 0, 1, 0, 3],
            }
            for domain, scores in samples.items():
                for index, score in enumerate(scores):
                    assessed_at = now - timedelta(days=len(scores) - index)
                    assessment_id = f"demo-history-{domain}-{assessed_at.date()}"
                    store.record_domain_assessment(
                        {
                            "assessment_id": assessment_id,
                            "domain": domain,
                            "score": score,
                            "status": "assessed",
                            "assessed_at": assessed_at.isoformat(),
                            "policy_revision": policy["revision"],
                            "policy_digest": digest,
                            "payload_json": json.dumps(
                                {"demo": True, "score": score},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    )
                    created["history"] += 1
        build_snapshot(
            store,
            device_ref=device_ref,
            policy_path=policy_path,
            now=now,
            persist=True,
        )
    return created


def _seed_demo_archives(
    store: LongitudinalStore,
    *,
    device_ref: str,
    edge_policy_path: Path,
) -> int:
    """Generate visibly synthetic audiovisual clips through the real archive path."""

    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            "demo media requires the 'demo' or 'edge' optional dependencies"
        ) from error

    from .edge_monitor import (
        BufferedVideoFrame,
        EdgeSelectionPolicy,
        InMemoryEdgeSegment,
    )
    from .media_archive import archive_candidate_clip
    from .multidomain import candidate_from_row
    from .speech_backend import AudioBuffer

    policy = EdgeSelectionPolicy.load(edge_policy_path)
    before = len(store.fetch_media_archives())
    width, height = 384, 216
    duration_ms = round(
        (policy.archive_event_pre_seconds + policy.archive_event_post_seconds)
        * 1000
    )
    frame_interval_ms = round(1000 / policy.video_sample_fps)
    frame_count = max(1, duration_ms // frame_interval_ms)
    sample_count = round(duration_ms * policy.audio_sample_rate_hz / 1000)
    timeline = np.arange(sample_count, dtype=np.float32) / policy.audio_sample_rate_hz

    for clip_index, row in enumerate(store.fetch_domain_candidates()):
        candidate = candidate_from_row(row)
        frames: list[BufferedVideoFrame] = []
        accent = ((45, 113, 232), (132, 74, 244), (36, 160, 122))[
            clip_index % 3
        ]
        for frame_index in range(frame_count):
            progress = frame_index / max(1, frame_count - 1)
            canvas = np.full((height, width, 3), (248, 246, 240), dtype=np.uint8)
            cv2.rectangle(canvas, (0, 0), (width, 42), (24, 34, 48), -1)
            cv2.putText(
                canvas,
                "KANGSHIELD  SYNTHETIC DEMO",
                (14, 27),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                candidate.domain.value.upper(),
                (18, 74),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                accent,
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                "Owner-only event clip",
                (18, 99),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (76, 85, 99),
                1,
                cv2.LINE_AA,
            )
            if candidate.domain.value == "fall":
                fall_phase = min(1.0, max(0.0, (progress - 0.25) / 0.22))
                center_x = round(255 + 45 * fall_phase)
                center_y = round(102 + 72 * fall_phase)
                angle = round(82 * fall_phase)
                cv2.ellipse(
                    canvas,
                    (center_x, center_y),
                    (13, 30),
                    angle,
                    0,
                    360,
                    accent,
                    -1,
                )
                cv2.circle(
                    canvas,
                    (center_x, center_y - round(40 * (1 - fall_phase))),
                    10,
                    accent,
                    -1,
                )
                cv2.line(canvas, (165, 188), (355, 188), (157, 164, 174), 2)
            else:
                pulse = 7 + round(4 * np.sin(progress * 18 * np.pi))
                cv2.rectangle(canvas, (238, 104), (322, 184), accent, -1)
                cv2.circle(canvas, (280, 144), pulse, (255, 255, 255), 2)
                cv2.putText(
                    canvas,
                    "VOICE",
                    (250, 204),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (76, 85, 99),
                    1,
                    cv2.LINE_AA,
                )
            cv2.putText(
                canvas,
                f"{frame_index / policy.video_sample_fps:04.1f}s",
                (18, 194),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (76, 85, 99),
                1,
                cv2.LINE_AA,
            )
            encoded, jpeg = cv2.imencode(
                ".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 78]
            )
            if not encoded:
                raise RuntimeError("synthetic demo frame encoding failed")
            frames.append(
                BufferedVideoFrame(
                    timestamp_ms=frame_index * frame_interval_ms,
                    jpeg_bytes=jpeg.tobytes(),
                )
            )

        marker_start = policy.archive_event_pre_seconds - 1
        marker_end = policy.archive_event_pre_seconds + 3
        envelope = ((timeline > marker_start) & (timeline < marker_end)).astype(
            np.float32
        )
        carrier = np.sin(
            2 * np.pi * (360 + clip_index * 100) * timeline
        ).astype(np.float32)
        audio = (0.10 * carrier * envelope).astype(np.float32)
        segment_started_at = candidate.occurred_at - timedelta(
            seconds=policy.archive_event_pre_seconds
        )
        segment = InMemoryEdgeSegment(
            segment_id=f"demo-archive-{clip_index}-{candidate.candidate_id}",
            device_ref=device_ref,
            started_at=segment_started_at,
            ended_at=segment_started_at + timedelta(milliseconds=duration_ms),
            duration_ms=duration_ms,
            frames=tuple(frames),
            audio=AudioBuffer(
                samples=audio,
                sample_rate_hz=policy.audio_sample_rate_hz,
                duration_ms=duration_ms,
            ),
            frame_width=width,
            frame_height=height,
            cloud_recording_ref=f"cloud-recording:synthetic-demo-{clip_index}",
        )
        archive_candidate_clip(
            store,
            segment=segment,
            candidate=candidate,
            pre_seconds=policy.archive_event_pre_seconds,
            post_seconds=policy.archive_event_post_seconds,
            retention_days=policy.archive_retention_days,
            maximum_total_bytes=policy.archive_maximum_total_bytes,
            video_fps=policy.video_sample_fps,
        )
    return len(store.fetch_media_archives()) - before


def _daily_row(
    local_date: str,
    values: tuple[float, float, float, float],
    now: datetime,
) -> dict[str, Any]:
    presence, activity, speech, sleep = values
    return {
        "local_date": local_date,
        "eligible_segments": 4,
        "daytime_presence": presence,
        "activity_level": activity,
        "speech_interaction": speech,
        "sleep_regularity": sleep,
        "sleep_confirmed": 1,
        "source_refs_json": "[]",
        "updated_at": now.isoformat(),
    }


def _candidate(
    *,
    candidate_id: str,
    device_ref: str,
    domain: str,
    category: str,
    occurred_at: datetime,
    summary: str,
    payload: dict[str, Any],
    quality: float,
) -> dict[str, Any]:
    timestamp = occurred_at.isoformat()
    return {
        "candidate_id": candidate_id,
        "device_ref": device_ref,
        "domain": domain,
        "category": category,
        "occurred_at": timestamp,
        "evidence_refs_json": json.dumps(
            [f"demo-evidence:{candidate_id}"], ensure_ascii=False
        ),
        "evidence_summary_json": json.dumps([summary], ensure_ascii=False),
        "quality": quality,
        "review_status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
