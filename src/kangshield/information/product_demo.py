"""Synthetic, privacy-safe records for the local product demonstration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .longitudinal.store import DEFAULT_STORE_ROOT, LongitudinalStore
from .multidomain import DEFAULT_POLICY_PATH, build_snapshot, load_policy


def seed_product_demo(
    *,
    elder_ref: str,
    device_ref: str,
    store_root: Path = DEFAULT_STORE_ROOT,
    policy_path: Path = DEFAULT_POLICY_PATH,
    now: datetime | None = None,
) -> dict[str, int]:
    """Seed an idempotent demo without raw media or real-person data."""

    if not elder_ref.startswith("demo-") or not device_ref.startswith("demo-"):
        raise ValueError("demo mode requires demo-* elder and device references")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_day = now.astimezone().date()
    bucket = now.strftime("%Y%m%d%H")
    created = {"captures": 0, "daily_features": 0, "candidates": 0, "history": 0}
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
