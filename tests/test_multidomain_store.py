from __future__ import annotations

import json
import sqlite3

from kangshield.information.longitudinal.store import LongitudinalStore


def test_v1_database_migrates_forward_to_v3(tmp_path):
    elder_dir = tmp_path / "elder_a"
    elder_dir.mkdir()
    db = sqlite3.connect(elder_dir / "longitudinal.sqlite")
    db.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE observations (
            id INTEGER PRIMARY KEY, observed_at TEXT, bucket TEXT,
            indicator_id TEXT NOT NULL, group_id TEXT NOT NULL,
            source_modality TEXT NOT NULL, value REAL, unit TEXT NOT NULL,
            assessability TEXT NOT NULL, quality_status TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0, scenario_id TEXT,
            time_start_at TEXT, time_end_at TEXT, source_ref TEXT NOT NULL,
            run_id TEXT, report_digest TEXT NOT NULL,
            limitations_json TEXT NOT NULL DEFAULT '[]',
            quality_metrics_json TEXT NOT NULL DEFAULT '{}',
            baseline_eligible INTEGER NOT NULL DEFAULT 0,
            UNIQUE (report_digest, indicator_id, observed_at)
        );
        CREATE TABLE episodes (
            id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, kind TEXT NOT NULL,
            start_at TEXT, end_at TEXT, detected_at TEXT, trigger_path TEXT,
            candidate_version TEXT, source_ref TEXT NOT NULL, run_id TEXT,
            report_digest TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE (report_digest, candidate_id)
        );
        """
    )
    db.close()
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        version = store._connection.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert version == "3"
        observation_columns = {
            row[1] for row in store._connection.execute("PRAGMA table_info(observations)")
        }
        assert "device_ref" in observation_columns
        assert store._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='domain_candidates'"
        ).fetchone()
        assert store._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='wellbeing_checkins'"
        ).fetchone()


def test_monthly_wellbeing_checkin_is_upserted_and_persistent(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        store.upsert_wellbeing_checkin(
            checkin_month="2026-08",
            completed_at="2026-08-30T10:00:00+08:00",
            answers=[2, 2, 2, 2, 2],
            raw_score=10,
            percentage_score=40,
            instrument_id="WHO-5",
            instrument_revision="WHO/UCN/MSD/MHE/2024.1",
        )
        store.upsert_wellbeing_checkin(
            checkin_month="2026-08",
            completed_at="2026-08-30T10:05:00+08:00",
            answers=[4, 4, 4, 4, 4],
            raw_score=20,
            percentage_score=80,
            instrument_id="WHO-5",
            instrument_revision="WHO/UCN/MSD/MHE/2024.1",
        )
        assert store.counts()["wellbeing_checkins"] == 1
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        row = store.fetch_wellbeing_checkins()[0]
        assert row["raw_score"] == 20
        assert json.loads(row["answers_json"]) == [4, 4, 4, 4, 4]
        assert store.delete_wellbeing_checkin("2026-08") is True
        assert store.fetch_wellbeing_checkins() == []


def test_review_is_persistent_auditable_and_delete_elder_is_complete(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        assert store.upsert_domain_candidate(
            {
                "candidate_id": "candidate-1",
                "device_ref": "target-camera",
                "domain": "fall",
                "category": "fall_candidate",
                "occurred_at": "2026-08-19T00:00:00+00:00",
                "evidence_refs_json": json.dumps(["feature:1"]),
                "created_at": "2026-08-19T00:00:00+00:00",
                "updated_at": "2026-08-19T00:00:00+00:00",
            }
        )
        store.review_candidate(
            candidate_id="candidate-1",
            decision="confirmed",
            decided_at="2026-08-19T01:00:00+00:00",
            operator="owner",
            owner_note="private note",
        )
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        assert store.fetch_domain_candidates()[0]["review_status"] == "confirmed"
        assert store.fetch_candidate_reviews()[0]["owner_note"] == "private note"
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path)
    assert not (tmp_path / "elder_a").exists()
