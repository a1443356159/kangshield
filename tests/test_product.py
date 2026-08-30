from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

import kangshield.information.product as product_module
from kangshield.information.longitudinal.store import LongitudinalStore
from kangshield.information.contracts import CandidateReviewDecision
from kangshield.information.product import (
    ProductRuntime,
    _dashboard_html,
    _documentation_html,
    export_product_report,
    make_product_handler,
    serve_product,
)
from kangshield.information.product_demo import seed_product_demo


def _seed(store_root):
    with LongitudinalStore("elder_a", root=store_root) as store:
        now = datetime.now(timezone.utc).isoformat()
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
                "payload_json": json.dumps(
                    {"transcript_excerpt": "请立即转账到安全账户 private transcript"}
                ),
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


def test_dashboard_is_submission_ready_and_self_contained():
    rendered = _dashboard_html("safe-token")
    assert "<title>康盾</title>" in rendered
    assert "需要关注的三件事" in rendered
    assert "我的日常基线" in rendered
    assert "本月幸福感自评" in rendered
    assert "保存并更新风险" in rendered
    assert 'href="/docs"' in rendered
    assert "/api/dashboard" in rendered
    assert "Promise.all" not in rendered
    assert "近期提醒" in rendered
    assert "播放异常片段" in rendered
    assert "云端事件回看" in rendered
    assert "pilot_unvalidated" not in rendered
    assert "global_score" not in rendered
    assert "KangShield" not in rendered
    assert "safe-token" in rendered
    assert "https://" not in rendered


def test_documentation_page_covers_terms_technology_and_privacy():
    rendered = _documentation_html()
    assert "<title>康盾 · 使用说明与服务条款</title>" in rendered
    assert "服务性质与使用约定" in rendered
    assert "隐私与数据" in rendered
    assert "技术路线" in rendered
    assert "风险等级说明" in rendered
    assert "WHO-5" in rendered
    assert "不是紧急服务" in rendered
    assert 'href="/"' in rendered


def test_dashboard_aggregate_uses_one_store_connection(tmp_path, monkeypatch):
    store_root = tmp_path / "store"
    _seed(store_root)
    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target-camera-secret",
        store_root=store_root,
    )
    real_store = LongitudinalStore
    opened = []

    def counted_store(*args, **kwargs):
        opened.append((args, kwargs))
        return real_store(*args, **kwargs)

    monkeypatch.setattr(product_module, "LongitudinalStore", counted_store)
    payload = runtime.dashboard()
    assert len(opened) == 1
    assert len(payload["snapshot"]["assessments"]) == 3
    assert payload["candidates"][0]["candidate_id"] == "fall-1"
    assert payload["profile"]["comparison_label"] == "与过去 28 天的自己相比"
    assert payload["wellbeing_checkin"]["affects_mental_risk"] is True


def test_demo_seed_requires_demo_refs_and_populates_all_domains(tmp_path):
    with pytest.raises(ValueError, match="demo-\\*"):
        seed_product_demo(
            elder_ref="real-elder",
            device_ref="demo-device",
            store_root=tmp_path,
        )
    seeded = seed_product_demo(
        elder_ref="demo-elder",
        device_ref="demo-device",
        store_root=tmp_path,
    )
    assert seeded["captures"] == 1
    assert seeded["candidates"] == 3
    runtime = ProductRuntime(
        elder_ref="demo-elder",
        device_ref="demo-device",
        store_root=tmp_path,
    )
    snapshot = runtime.snapshot()
    scores = {item.domain.value: item.score for item in snapshot.assessments}
    assert scores == {"fall": 2, "mental_wellbeing": 2, "fraud": 3}
    assert len(runtime.trends()) >= 27
    profile = runtime.personal_profile()
    assert profile["ready"] is True
    assert profile["comparison_label"] == "与过去 28 天的自己相比"
    assert any(
        item["key"] == "daytime_presence"
        and item["state"] == "significant_change"
        for item in profile["features"]
    )
    transcripts = {
        item.get("transcript_excerpt") for item in runtime.candidates()
    }
    assert "请立即把钱转到安全账户，我来帮您处理。" in transcripts


def test_review_api_requires_json_same_origin_and_csrf(tmp_path):
    _seed(tmp_path / "store")
    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target-camera-secret",
        store_root=tmp_path / "store",
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
        with urllib.request.urlopen(origin + "/api/dashboard") as response:
            dashboard = json.load(response)
        assert len(dashboard["snapshot"]["assessments"]) == 3
        assert set(dashboard) == {
            "schema_version",
            "generated_at",
            "snapshot",
            "candidates",
            "trends",
            "profile",
            "wellbeing_checkin",
            "monitor",
        }
        assert dashboard["monitor"]["raw_media_persisted"] is False
        with urllib.request.urlopen(origin + "/docs") as response:
            docs_page = response.read().decode("utf-8")
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
            assert response.headers["Permissions-Policy"] == (
                "camera=(), microphone=(), geolocation=()"
            )
        assert "服务性质与使用约定" in docs_page
        with urllib.request.urlopen(origin + "/api/profile") as response:
            profile = json.load(response)
        assert profile["comparison_label"] == "与过去 28 天的自己相比"
        assert "daytime_presence" not in json.dumps(profile)
        with urllib.request.urlopen(origin + "/api/wellbeing-checkin") as response:
            checkin = json.load(response)
        assert checkin["due"] is True
        assert checkin["affects_mental_risk"] is True
        assert len(checkin["instrument"]["questions"]) == 5
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

        low_checkin = urllib.request.Request(
            origin + "/api/wellbeing-checkin",
            data=json.dumps({"answers": [2, 2, 2, 2, 2]}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-CSRF-Token": runtime.csrf_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(low_checkin) as response:
            saved = json.load(response)
        assert saved["checkin"]["due"] is False
        assert saved["checkin"]["current"]["percentage_score"] == 40
        mental = next(
            item
            for item in saved["snapshot"]["assessments"]
            if item["domain"] == "mental_wellbeing"
        )
        assert mental["score"] == 2

        replace_checkin = urllib.request.Request(
            origin + "/api/wellbeing-checkin",
            data=json.dumps({"answers": [5, 5, 5, 5, 5]}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-CSRF-Token": runtime.csrf_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(replace_checkin) as response:
            replaced = json.load(response)
        assert replaced["checkin"]["current"]["percentage_score"] == 100
        mental = next(
            item
            for item in replaced["snapshot"]["assessments"]
            if item["domain"] == "mental_wellbeing"
        )
        assert mental["score"] == 0

        delete_checkin = urllib.request.Request(
            origin + "/api/wellbeing-checkin",
            headers={
                "Origin": origin,
                "X-CSRF-Token": runtime.csrf_token,
            },
            method="DELETE",
        )
        with urllib.request.urlopen(delete_checkin) as response:
            deleted = json.load(response)
        assert deleted["checkin"]["due"] is True
        mental = next(
            item
            for item in deleted["snapshot"]["assessments"]
            if item["domain"] == "mental_wellbeing"
        )
        assert mental["score"] is None
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


def test_candidate_cloud_playback_is_on_demand_and_not_persisted(tmp_path):
    store_root = tmp_path / "store"
    started = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)
    occurred = started + timedelta(seconds=30)
    with LongitudinalStore("elder_a", root=store_root) as store:
        store.record_edge_segment(
            {
                "segment_id": "edge-1",
                "device_ref": "target",
                "segment_started_at": started.isoformat(),
                "segment_ended_at": (started + timedelta(seconds=60)).isoformat(),
                "status": "completed",
                "failure_code": None,
                "cloud_recording_ref": "cloud-recording:opaque",
                "selector_revision": "r1",
                "selector_digest": "a" * 64,
                "raw_media_persisted": 0,
                "endpoint_value_persisted": 0,
                "screened_video_seconds": 60,
                "screened_audio_seconds": 60,
                "selected_pose_seconds": 5,
                "selected_asr_seconds": 5,
                "screened_frame_count": 300,
                "selected_frame_count": 25,
                "candidate_count": 1,
                "key_windows_json": "[]",
                "limitations_json": "[]",
                "created_at": started.isoformat(),
            }
        )
        store.upsert_domain_candidate(
            {
                "candidate_id": "event-1",
                "device_ref": "target",
                "domain": "fraud",
                "category": "fraud_language",
                "occurred_at": occurred.isoformat(),
                "evidence_refs_json": json.dumps(["edge:edge-1"]),
                "evidence_summary_json": "[]",
                "created_at": occurred.isoformat(),
                "updated_at": occurred.isoformat(),
                "payload_json": json.dumps({"segment_id": "edge-1"}),
            }
        )
    calls = []

    def playback(start, end):
        calls.append((start, end))
        return "https://open.ys7.com/event/private-signed.m3u8"

    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target",
        store_root=store_root,
        playback_provider=playback,
    )

    assert runtime.candidates()[0]["playback_available"] is True
    payload = runtime.cloud_playback("event-1")
    assert payload["locally_persisted"] is False
    assert payload["url"].endswith("private-signed.m3u8")
    assert calls == [
        (
            occurred - timedelta(seconds=10),
            occurred + timedelta(seconds=20),
        )
    ]
    serialized = (store_root / "elder_a" / "longitudinal.sqlite").read_bytes()
    assert b"private-signed.m3u8" not in serialized

    placeholder = type("Placeholder", (), {})
    server = ThreadingHTTPServer(("127.0.0.1", 0), placeholder)
    port = server.server_port
    server.server_close()
    origin = f"http://127.0.0.1:{port}"
    handler = make_product_handler(runtime, host="127.0.0.1", port=port)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        missing_csrf = urllib.request.Request(
            origin + "/api/candidates/event-1/playback",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(missing_csrf)
        assert caught.value.code == 403

        request = urllib.request.Request(
            origin + "/api/candidates/event-1/playback",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-CSRF-Token": runtime.csrf_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            over_http = json.load(response)
            assert response.headers["Cache-Control"] == "no-store"
        assert over_http["url"].endswith("private-signed.m3u8")
        assert over_http["locally_persisted"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_continuous_runtime_does_not_block_on_missing_stream_endpoint(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("KANG_TEST_MISSING_ENDPOINT", raising=False)

    runtime = ProductRuntime(
        elder_ref="elder_a",
        device_ref="target",
        store_root=tmp_path / "store",
        continuous=True,
        edge_provider="endpoint_env",
        edge_endpoint_env="KANG_TEST_MISSING_ENDPOINT",
        cloud_playback_provider="none",
    )

    assert runtime.edge_monitor is not None
    assert runtime.last_edge_segment == {"status": "not_started"}
    runtime.stop()


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
        store.upsert_wellbeing_checkin(
            checkin_month=datetime.now().astimezone().strftime("%Y-%m"),
            completed_at=datetime.now().astimezone().isoformat(),
            answers=[2, 2, 2, 2, 2],
            raw_score=10,
            percentage_score=40,
            instrument_id="WHO-5",
            instrument_revision="WHO/UCN/MSD/MHE/2024.1",
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
    assert "请立即转账到安全账户 private transcript" in owner_json.read_text()
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
            "transcript_excerpt",
            "请立即转账到安全账户 private transcript",
            "answers_json",
            "percentage_score",
            "wellbeing_checkins",
        ):
        assert forbidden not in serialized
    payload = json.loads(public_json.read_text())
    assert payload["global_score"] is None
    assert {item["domain"] for item in payload["assessments"]} == {
        "fall",
        "mental_wellbeing",
        "fraud",
    }
