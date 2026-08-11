from __future__ import annotations

import sqlite3
import stat

import pytest

from kangshield.information.longitudinal.store import LongitudinalStore


def _observation_row(**overrides):
    row = {
        "observed_at": "2026-08-01T10:00:00+08:00",
        "bucket": "day",
        "indicator_id": "gait_speed",
        "group_id": "gait",
        "source_modality": "video",
        "value": 1.05,
        "unit": "m/s",
        "assessability": "assessable",
        "quality_status": "pass",
        "sample_count": 3,
        "scenario_id": "C02",
        "time_start_at": "2026-08-01T10:00:00+08:00",
        "time_end_at": "2026-08-01T10:00:18+08:00",
        "source_ref": "sha256:" + "0" * 64,
        "run_id": "run-1",
        "report_digest": "a" * 64,
        "limitations_json": "[]",
        "quality_metrics_json": "{}",
        "baseline_eligible": 1,
    }
    row.update(overrides)
    return row


def test_elder_ref_validation():
    with pytest.raises(ValueError):
        LongitudinalStore("../escape")
    with pytest.raises(ValueError):
        LongitudinalStore("")
    with pytest.raises(ValueError):
        LongitudinalStore("has space")


def test_store_creates_schema_and_owner_only_permissions(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        tables = {
            row[0]
            for row in store._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "meta",
            "ingest_ledger",
            "observations",
            "episodes",
            "baselines",
            "deviation_candidates",
        } <= tables
        dir_mode = stat.S_IMODE(store.elder_dir.stat().st_mode)
        db_mode = stat.S_IMODE(store.db_path.stat().st_mode)
        assert dir_mode == 0o700
        assert db_mode == 0o600


def test_ingest_ledger_makes_reingest_idempotent(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        assert store.already_ingested("b" * 64) is None
        store.record_ingest(
            report_digest="b" * 64,
            ingested_at="2026-08-01T00:00:00+00:00",
            report_kind="indicator_extraction",
            run_id="run-1",
            observation_count=2,
            episode_count=0,
        )
        assert store.already_ingested("b" * 64) == "indicator_extraction"
        with pytest.raises(sqlite3.IntegrityError):
            store.record_ingest(
                report_digest="b" * 64,
                ingested_at="2026-08-01T00:00:01+00:00",
                report_kind="indicator_extraction",
                run_id="run-1",
                observation_count=2,
                episode_count=0,
            )


def test_observation_insert_is_row_idempotent(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        first = store.insert_observations([_observation_row()])
        second = store.insert_observations([_observation_row()])
        assert first == 1
        assert second == 0
        assert store.counts()["observations"] == 1


def test_delete_elder_removes_only_that_elder(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path):
        pass
    with LongitudinalStore("elder_b", root=tmp_path):
        pass
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is True
    assert not (tmp_path / "elder_a").exists()
    assert (tmp_path / "elder_b").is_dir()
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is False
