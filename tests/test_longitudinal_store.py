from __future__ import annotations

from datetime import datetime, timedelta, timezone
import stat

import pytest

from kangshield.information.longitudinal.store import LongitudinalStore
from kangshield.information.media_archive import (
    MediaArchiveError,
    candidate_archive_path,
    prune_candidate_archives,
)


def test_elder_ref_rejects_path_escape_and_ambiguous_names(tmp_path):
    for value in ("../escape", "", "has space", "/absolute"):
        with pytest.raises(ValueError):
            LongitudinalStore(value, root=tmp_path)


def test_store_rejects_symlinked_elder_directory_and_database(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "elder_link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        LongitudinalStore("elder_link", root=tmp_path)
    with pytest.raises(ValueError, match="symbolic link"):
        LongitudinalStore.delete_elder("elder_link", root=tmp_path)

    elder_dir = tmp_path / "elder_db"
    elder_dir.mkdir()
    outside_database = outside / "outside.sqlite"
    outside_database.touch()
    (elder_dir / "longitudinal.sqlite").symlink_to(outside_database)
    with pytest.raises(ValueError, match="database cannot be a symbolic link"):
        LongitudinalStore("elder_db", root=tmp_path)


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
            "candidate_media_archives",
            "domain_assessments",
            "candidate_reviews",
            "wellbeing_checkins",
        } <= tables
        assert stat.S_IMODE(store.elder_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(store.db_path.stat().st_mode) == 0o600


def test_archive_index_rejects_paths_outside_owner_directory(tmp_path):
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        with pytest.raises(ValueError, match="safe relative MP4"):
            store.record_candidate_media_archive(
                {
                    "archive_id": "a" * 64,
                    "candidate_id": "candidate-1",
                    "segment_id": "edge-1",
                    "device_ref": "target",
                    "relative_path": "../../private.mp4",
                    "mime_type": "video/mp4",
                    "started_at": "2026-08-30T00:00:00+00:00",
                    "ended_at": "2026-08-30T00:00:30+00:00",
                    "sha256": "b" * 64,
                    "byte_size": 1,
                    "has_video": 1,
                    "has_audio": 1,
                    "owner_only": 1,
                    "raw_stream_persisted": 0,
                    "created_at": "2026-08-30T00:00:30+00:00",
                    "retention_until": "2026-09-29T00:00:30+00:00",
                }
            )


def test_archive_retention_removes_expired_then_oldest_to_fit_cap(tmp_path):
    now = datetime.now(timezone.utc)
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        archive_dir = store.elder_dir / "anomaly_clips"
        archive_dir.mkdir(mode=0o700)
        for index, archive_id in enumerate(("a" * 64, "b" * 64)):
            candidate_id = f"candidate-{index}"
            store.upsert_domain_candidate(
                {
                    "candidate_id": candidate_id,
                    "device_ref": "target",
                    "domain": "fall",
                    "category": "fall_candidate",
                    "occurred_at": now.isoformat(),
                    "evidence_refs_json": "[]",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
            path = archive_dir / f"{archive_id}.mp4"
            path.write_bytes(bytes([index + 1]) * 10)
            path.chmod(0o600)
            store.record_candidate_media_archive(
                {
                    "archive_id": archive_id,
                    "candidate_id": candidate_id,
                    "segment_id": f"edge-{index}",
                    "device_ref": "target",
                    "relative_path": f"anomaly_clips/{archive_id}.mp4",
                    "mime_type": "video/mp4",
                    "started_at": now.isoformat(),
                    "ended_at": (now + timedelta(seconds=10)).isoformat(),
                    "sha256": "c" * 64,
                    "byte_size": 10,
                    "has_video": 1,
                    "has_audio": 1,
                    "owner_only": 1,
                    "raw_stream_persisted": 0,
                    "created_at": (now + timedelta(seconds=index)).isoformat(),
                    "retention_until": (now + timedelta(days=30)).isoformat(),
                }
            )

        assert prune_candidate_archives(
            store, now=now, maximum_total_bytes=15
        ) == 1
        assert not (archive_dir / f"{'a' * 64}.mp4").exists()
        assert (archive_dir / f"{'b' * 64}.mp4").is_file()
        assert len(store.fetch_media_archives()) == 1

        store._connection.execute(
            "UPDATE candidate_media_archives SET retention_until = ?",
            ((now - timedelta(seconds=1)).isoformat(),),
        )
        store._connection.commit()
        assert prune_candidate_archives(
            store, now=now, maximum_total_bytes=15
        ) == 1
        assert store.fetch_media_archives() == []


def test_archive_resolver_rejects_symlinked_media_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        (store.elder_dir / "anomaly_clips").symlink_to(
            outside, target_is_directory=True
        )
        row = {
            "archive_id": "a" * 64,
            "relative_path": f"anomaly_clips/{'a' * 64}.mp4",
            "byte_size": 1,
        }
        with pytest.raises(MediaArchiveError, match="symbolic link"):
            candidate_archive_path(store, row)


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
    with LongitudinalStore("elder_a", root=tmp_path) as store:
        archive_dir = store.elder_dir / "anomaly_clips"
        archive_dir.mkdir(mode=0o700)
        (archive_dir / "private.mp4").write_bytes(b"sensitive")
    with LongitudinalStore("elder_b", root=tmp_path):
        pass
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is True
    assert not (tmp_path / "elder_a").exists()
    assert (tmp_path / "elder_b").is_dir()
    assert LongitudinalStore.delete_elder("elder_a", root=tmp_path) is False
