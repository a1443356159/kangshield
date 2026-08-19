from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from kangshield.information.contracts import DomainCandidate
from kangshield.information.incremental_analysis import AnalysisResult, IncrementalAnalyzer
from kangshield.information.longitudinal.store import LongitudinalStore


def _capture_run(root, run_id, *, device_ref="target", ready=True, malformed=False):
    run = root / run_id
    (run / "reports").mkdir(parents=True)
    (run / "artifacts").mkdir()
    media = run / "artifacts" / "stream-capture.mkv"
    media.write_bytes(f"media-{run_id}".encode())
    moment = "2026-08-19T00:00:00+00:00"
    manifest = {
        "run_id": run_id,
        "status": "completed",
        "started_at": moment,
        "finished_at": "2026-08-19T00:01:00+00:00",
    }
    report = {
        "capture_started_at": moment,
        "capture_ended_at": "2026-08-19T00:01:00+00:00",
        "capture_artifact_ready": ready,
        "same_container_multimodal_ready": ready,
        "output_artifact": "../escape" if malformed else "artifacts/stream-capture.mkv",
        "media_probe": {"observation": {"device_ref": device_ref}},
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "reports" / "stream-capture.json").write_text(json.dumps(report))
    return media


def test_scanner_filters_target_is_idempotent_and_retries_failure(tmp_path):
    runs = tmp_path / "runs"
    media = _capture_run(runs, "run-target")
    _capture_run(runs, "run-aux", device_ref="aux")
    _capture_run(runs, "run-missing", ready=False)
    calls = {"count": 0}

    def analyze(path, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("model missing")
        return AnalysisResult(
            pose_quality_seconds=60,
            audio_valid_seconds=60,
            eligible_segments=1,
            daytime_presence=0.8,
            activity_level=0.5,
            speech_interaction=2,
            candidates=[
                (
                    DomainCandidate(
                        candidate_id="fraud-1",
                        domain="fraud",
                        category="fraud_language",
                        occurred_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
                        evidence_refs=["feature:1"],
                    ),
                    {"categories": ["credential_request"]},
                )
            ],
        )

    scanner = IncrementalAnalyzer(
        elder_ref="elder_a",
        device_ref="target",
        store_root=tmp_path / "store",
        runs_dir=runs,
        policy_path="configs/v2-multidomain-risk-policy.json",
        media_analyzer=analyze,
    )
    now = datetime(2026, 8, 19, 2, tzinfo=timezone.utc)
    first = scanner.scan_once(now=now)
    assert first == {"discovered": 3, "completed": 0, "skipped": 2, "failed": 1}
    second = scanner.scan_once(now=now)
    assert second["completed"] == 1
    third = scanner.scan_once(now=now)
    assert third["completed"] == 0
    assert calls["count"] == 2
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        row = store._connection.execute(
            "SELECT status, attempts FROM analysis_ledger WHERE media_digest=?", (digest,)
        ).fetchone()
        assert tuple(row) == ("completed", 2)
        assert len(store.fetch_domain_candidates()) == 1
        assert store.fetch_daily_features()[0]["eligible_segments"] == 1
