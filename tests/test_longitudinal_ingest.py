from __future__ import annotations

import json

import pytest

from kangshield.information.indicators import (
    extract_sleep_indicators,
    extract_video_indicators,
)
from kangshield.information.longitudinal.ingest import (
    CLIP_RELATIVE_TIMING_LIMITATION,
    ingest_report,
    ingest_reports,
)
from kangshield.information.longitudinal.store import LongitudinalStore

VIDEO_FIXTURE = "tests/fixtures/indicators/video-indicators.synthetic.json"
SLEEP_FIXTURE = "tests/fixtures/sleep/sdhy1-export.synthetic.json"


def _write_report(tmp_path, name: str, report) -> object:
    path = tmp_path / name
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


def test_video_fixture_ingest_excludes_timestamp_less_observations(tmp_path):
    report = extract_video_indicators(VIDEO_FIXTURE)
    path = _write_report(tmp_path, "video.json", report)
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        entry = ingest_report(path, elder_ref="elder_a", store=store)
        assert entry.status == "ingested"
        assert entry.report_kind == "indicator_extraction"
        assert entry.observation_count == len(report.observations)
        # The video fixture carries only clip-relative ms, so nothing is
        # baseline-eligible (fail-closed on missing timezone-aware time).
        assert entry.baseline_excluded_count == len(report.observations)
        counts = store.counts()
        assert counts["baseline_eligible_observations"] == 0


def test_sleep_fixture_ingest_keeps_trend_values_eligible(tmp_path):
    report = extract_sleep_indicators(SLEEP_FIXTURE)
    path = _write_report(tmp_path, "sleep.json", report)
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        entry = ingest_report(path, elder_ref="elder_a", store=store)
        assert entry.status == "ingested"
        assert entry.observation_count == len(report.observations)
        counts = store.counts()
        # heart-rate + respiratory trends are assessable with tz timestamps;
        # bedtime/wake/duration stay blocked_semantics and are excluded.
        assert counts["baseline_eligible_observations"] == 2
        rows = store.fetch_eligible_values("sleep_heart_rate_trend", "night")
        assert len(rows) == 1
        assert rows[0]["value"] == pytest.approx(67.5)


def test_reingest_same_report_is_skipped(tmp_path):
    path = _write_report(tmp_path, "sleep.json", extract_sleep_indicators(SLEEP_FIXTURE))
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        report = ingest_reports([path, path], elder_ref="elder_a", store=store)
        assert report.ingested_count == 1
        assert report.skipped_duplicate_count == 1
        assert store.counts()["observations"] == 5


def test_fall_candidate_prediction_set_ingest_stores_clip_relative_episodes(tmp_path):
    payload = {
        "schema_version": "1.0",
        "prediction_set_id": "prediction-set-1",
        "variant_id": "rtmpose-v1",
        "source_run_id": "run-9",
        "capture_manifest_sha256": "a" * 64,
        "model_policy_sha256": "b" * 64,
        "fall_feature_policy_sha256": "c" * 64,
        "candidate_generator_policy_sha256": "d" * 64,
        "generated_at": "2026-08-01T00:00:00+00:00",
        "clips": [
            {
                "scenario_id": "C11",
                "duration_ms": 6000,
                "candidates": [
                    {
                        "candidate_id": "cand-1",
                        "start_ms": 1200,
                        "end_ms": 2600,
                        "detected_at_ms": 2000,
                    }
                ],
            }
        ],
    }
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        report = ingest_reports([path], elder_ref="elder_a", store=store)
        entry = report.entries[0]
        assert entry.report_kind == "fall_candidate_prediction_set"
        assert entry.episode_count == 1
        assert CLIP_RELATIVE_TIMING_LIMITATION in report.limitations
        assert store.counts()["episodes"] == 1


def test_unrecognized_report_shape_is_rejected(tmp_path):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        with pytest.raises(ValueError, match="unrecognized longitudinal report"):
            ingest_report(path, elder_ref="elder_a", store=store)
