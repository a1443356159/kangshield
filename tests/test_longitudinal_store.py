from __future__ import annotations

import stat

import pytest

from kangshield.information.longitudinal.store import LongitudinalStore


def test_elder_ref_rejects_path_escape_and_ambiguous_names(tmp_path):
    for value in ("../escape", "", "has space", "/absolute"):
        with pytest.raises(ValueError):
            LongitudinalStore(value, root=tmp_path)


def test_final_store_schema_and_permissions_are_owner_only(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        tables = {
            row[0]
            for row in store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "analysis_ledger",
            "edge_segment_audits",
            "daily_features",
            "domain_candidates",
            "domain_assessments",
            "candidate_reviews",
            "wellbeing_checkins",
        } <= tables
        assert stat.S_IMODE(store.elder_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(store.db_path.stat().st_mode) == 0o600


def test_analysis_ledger_retries_are_idempotent_by_media_digest(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        common = {
            "media_digest": "a" * 64,
            "report_digest": "b" * 64,
            "run_id": "edge-1",
            "device_ref": "target",
            "captured_start_at": "2026-08-30T00:00:00+00:00",
            "captured_end_at": "2026-08-30T00:01:00+00:00",
        }
        store.record_analysis_attempt(
            **common,
            attempted_at="2026-08-30T00:01:01+00:00",
            status="failed",
            error="speech_model_failed",
        )
        store.record_analysis_attempt(
            **common,
            attempted_at="2026-08-30T00:02:01+00:00",
            status="completed",
            pose_quality_seconds=10,
            audio_valid_seconds=12,
        )
        row = store._connection.execute(
            "SELECT * FROM analysis_ledger WHERE media_digest = ?", ("a" * 64,)
        ).fetchone()
        assert row["attempts"] == 2
        assert row["status"] == "completed"
        assert store.analysis_status("a" * 64) == "completed"


def test_delete_elder_removes_only_the_confirmed_person(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path):
        pass
    with LongitudinalStore("elder_b", root=tmp_path):
        pass
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is True
    assert not (tmp_path / "elder_a").exists()
    assert (tmp_path / "elder_b").is_dir()
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is False
