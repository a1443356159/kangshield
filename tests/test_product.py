from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

import pytest

from kangshield.information.longitudinal.store import LongitudinalStore
from kangshield.information.contracts import CandidateReviewDecision
from kangshield.information.product import (
    ProductRuntime,
    export_product_report,
    make_product_handler,
    serve_product,
)


def _seed(store_root):
    with LongitudinalStore("elder_a", root=store_root) as store:
        now = "2026-08-19T00:00:00+00:00"
        store.record_analysis_attempt(
            media_digest="a" * 64,
            report_digest="b" * 64,
            run_id="run-1",
            device_ref="target-camera-secret",
            attempted_at=now,
            captured_start_at=now,
            captured_end_at=now,
            status="completed",
            pose_quality_seconds=600,
            audio_valid_seconds=600,
        )
        store.upsert_domain_candidate(
            {
                "candidate_id": "fall-1",
                "device_ref": "target-camera-secret",
                "domain": "fall",
                "category": "fall_candidate",
                "occurred_at": now,
                "evidence_refs_json": json.dumps(["local/path/private.mkv"]),
                "evidence_summary_json": json.dumps(["candidate"]),
                "created_at": now,
                "updated_at": now,
            }
        )


def test_serve_product_rejects_non_loopback(tmp_path):
    with pytest.raises(ValueError, match="127.0.0.1"):
        serve_product(
            elder_ref="elder_a",
            device_ref="target",
            host="0.0.0.0",
            store_root=tmp_path,
        )


def test_review_api_requires_json_same_origin_and_csrf(tmp_path):
    _seed(tmp_path / "store")
    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target-camera-secret",
        store_root=tmp_path / "store",
        runs_dir=tmp_path / "runs",
    )
    placeholder = type("Placeholder", (), {})
    server = ThreadingHTTPServer(("127.0.0.1", 0), placeholder)
    port = server.server_port
    server.server_close()
    handler = make_product_handler(runtime, host="127.0.0.1", port=port)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(origin + "/api/snapshot") as response:
            snapshot = json.load(response)
        assert len(snapshot["assessments"]) == 3
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(origin + "/../../etc/passwd")
        assert missing.value.code == 404
        payload = json.dumps(
            {"decision": "confirmed", "operator": "owner", "owner_note": "note"}
        ).encode()
        bad = urllib.request.Request(
            origin + "/api/candidates/fall-1/review",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(bad)
        assert caught.value.code == 403
        good = urllib.request.Request(
            origin + "/api/candidates/fall-1/review",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-CSRF-Token": runtime.csrf_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(good) as response:
            reviewed = json.load(response)
        fall = next(
            item for item in reviewed["snapshot"]["assessments"] if item["domain"] == "fall"
        )
        assert fall["score"] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_reviews_remain_auditable(tmp_path):
    _seed(tmp_path / "store")
    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target-camera-secret",
        store_root=tmp_path / "store",
        runs_dir=tmp_path / "runs",
    )

    def decide(value):
        return runtime.review(
            CandidateReviewDecision(
                candidate_id="fall-1",
                decision=value,
                operator=f"owner-{value}",
                owner_note=f"note-{value}",
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ["confirmed", "rejected"]))
    assert len(results) == 2
    with LongitudinalStore("elder_a", root=tmp_path / "store") as store:
        reviews = store.fetch_candidate_reviews("fall-1")
        assert {row["decision"] for row in reviews} == {"confirmed", "rejected"}
        assert len(reviews) == 2


def test_public_export_is_redacted_and_owner_export_keeps_audit(tmp_path):
    store_root = tmp_path / "store"
    _seed(store_root)
    with LongitudinalStore("elder_a", root=store_root) as store:
        store.review_candidate(
            candidate_id="fall-1",
            decision="confirmed",
            decided_at=datetime.now(timezone.utc).isoformat(),
            operator="owner-secret",
            owner_note="private note secret",
        )
    owner_html, owner_json = export_product_report(
        elder_ref="elder_a",
        device_ref="target-camera-secret",
        visibility="owner_only",
        output=tmp_path / "owner",
        store_root=store_root,
    )
    public_html, public_json = export_product_report(
        elder_ref="elder_a",
        device_ref=None,
        visibility="public_evidence",
        output=tmp_path / "public",
        store_root=store_root,
    )
    assert owner_html.is_file() and owner_json.is_file()
    assert "private note secret" in owner_json.read_text()
    serialized = public_json.read_text() + public_html.read_text()
    for forbidden in (
        "elder_a",
        "target-camera-secret",
        "private note secret",
        "owner-secret",
        "private.mkv",
        "evidence_refs",
        "occurred_at",
        "owner_note",
    ):
        assert forbidden not in serialized
    payload = json.loads(public_json.read_text())
    assert payload["global_score"] is None
    assert {item["domain"] for item in payload["assessments"]} == {
        "fall",
        "mental_wellbeing",
        "fraud",
    }
