"""Owner-only per-elder longitudinal SQLite store.

One database file per elder under ``data/processed/longitudinal/<elder_ref>/``;
deleting an elder's directory is the complete erasure path. The store keeps
indicator observations, L0 candidate episodes, L1 personal baselines and
baseline-deviation candidates. It never stores raw media or transcript text.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "1"
DEFAULT_STORE_ROOT = Path("data/processed/longitudinal")

_ELDER_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_ledger (
    report_digest TEXT PRIMARY KEY,
    ingested_at TEXT NOT NULL,
    report_kind TEXT NOT NULL,
    run_id TEXT,
    observation_count INTEGER NOT NULL DEFAULT 0,
    episode_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    observed_at TEXT,
    bucket TEXT,
    indicator_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    source_modality TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL,
    assessability TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    scenario_id TEXT,
    time_start_at TEXT,
    time_end_at TEXT,
    source_ref TEXT NOT NULL,
    run_id TEXT,
    report_digest TEXT NOT NULL,
    limitations_json TEXT NOT NULL DEFAULT '[]',
    quality_metrics_json TEXT NOT NULL DEFAULT '{}',
    baseline_eligible INTEGER NOT NULL DEFAULT 0,
    UNIQUE (report_digest, indicator_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_observations_baseline
    ON observations (indicator_id, bucket, baseline_eligible, observed_at);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_at TEXT,
    end_at TEXT,
    detected_at TEXT,
    trigger_path TEXT,
    candidate_version TEXT,
    source_ref TEXT NOT NULL,
    run_id TEXT,
    report_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (report_digest, candidate_id)
);
CREATE TABLE IF NOT EXISTS baselines (
    indicator_id TEXT NOT NULL,
    bucket TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    median REAL,
    mad REAL,
    ewma REAL,
    policy_revision TEXT NOT NULL,
    PRIMARY KEY (indicator_id, bucket)
);
CREATE TABLE IF NOT EXISTS deviation_candidates (
    id INTEGER PRIMARY KEY,
    candidate_id TEXT NOT NULL UNIQUE,
    detected_at TEXT NOT NULL,
    indicator_id TEXT NOT NULL,
    bucket TEXT NOT NULL,
    direction TEXT NOT NULL,
    z_value REAL NOT NULL,
    ewma_shift REAL,
    score INTEGER NOT NULL,
    policy_revision TEXT NOT NULL,
    policy_digest TEXT NOT NULL,
    baseline_sample_count INTEGER NOT NULL,
    limitations_json TEXT NOT NULL DEFAULT '[]'
);
"""


def validate_elder_ref(elder_ref: str) -> str:
    if not _ELDER_REF_PATTERN.match(elder_ref):
        raise ValueError(
            "elder_ref must be 1-64 chars of [A-Za-z0-9_-], starting alphanumeric"
        )
    return elder_ref


class LongitudinalStore:
    def __init__(self, elder_ref: str, root: Path = DEFAULT_STORE_ROOT) -> None:
        self.elder_ref = validate_elder_ref(elder_ref)
        self.elder_dir = Path(root) / self.elder_ref
        self.elder_dir.mkdir(parents=True, exist_ok=True)
        self.elder_dir.chmod(0o700)
        self.db_path = self.elder_dir / "longitudinal.sqlite"
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(_SCHEMA)
        self._connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self._connection.commit()
        self.db_path.chmod(0o600)

    def __enter__(self) -> "LongitudinalStore":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @classmethod
    def delete_elder(cls, elder_ref: str, root: Path = DEFAULT_STORE_ROOT) -> bool:
        """Erase one elder's entire store. Returns True when a directory was removed."""
        safe_ref = validate_elder_ref(elder_ref)
        elder_dir = Path(root) / safe_ref
        if not elder_dir.is_dir():
            return False
        shutil.rmtree(elder_dir)
        return True

    def already_ingested(self, report_digest: str) -> str | None:
        row = self._connection.execute(
            "SELECT report_kind FROM ingest_ledger WHERE report_digest = ?",
            (report_digest,),
        ).fetchone()
        return None if row is None else str(row["report_kind"])

    def record_ingest(
        self,
        *,
        report_digest: str,
        ingested_at: str,
        report_kind: str,
        run_id: str | None,
        observation_count: int,
        episode_count: int,
    ) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO ingest_ledger (report_digest, ingested_at, report_kind,"
                " run_id, observation_count, episode_count)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report_digest,
                    ingested_at,
                    report_kind,
                    run_id,
                    observation_count,
                    episode_count,
                ),
            )

    def insert_observations(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = [
            "observed_at",
            "bucket",
            "indicator_id",
            "group_id",
            "source_modality",
            "value",
            "unit",
            "assessability",
            "quality_status",
            "sample_count",
            "scenario_id",
            "time_start_at",
            "time_end_at",
            "source_ref",
            "run_id",
            "report_digest",
            "limitations_json",
            "quality_metrics_json",
            "baseline_eligible",
        ]
        placeholder = ", ".join("?" for _ in columns)
        statement = (
            f"INSERT OR IGNORE INTO observations ({', '.join(columns)})"
            f" VALUES ({placeholder})"
        )
        with self._connection:
            cursor = self._connection.executemany(
                statement, [tuple(row[column] for column in columns) for row in rows]
            )
        return cursor.rowcount

    def insert_episodes(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = [
            "candidate_id",
            "kind",
            "start_at",
            "end_at",
            "detected_at",
            "trigger_path",
            "candidate_version",
            "source_ref",
            "run_id",
            "report_digest",
            "payload_json",
        ]
        placeholder = ", ".join("?" for _ in columns)
        statement = (
            f"INSERT OR IGNORE INTO episodes ({', '.join(columns)})"
            f" VALUES ({placeholder})"
        )
        with self._connection:
            cursor = self._connection.executemany(
                statement, [tuple(row[column] for column in columns) for row in rows]
            )
        return cursor.rowcount

    def fetch_eligible_values(
        self,
        indicator_id: str,
        bucket: str,
    ) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT observed_at, value FROM observations"
                " WHERE indicator_id = ? AND bucket = ? AND baseline_eligible = 1"
                " ORDER BY observed_at",
                (indicator_id, bucket),
            )
        )

    def upsert_baseline(self, row: dict[str, Any]) -> None:
        columns = [
            "indicator_id",
            "bucket",
            "computed_at",
            "window_days",
            "sample_count",
            "status",
            "median",
            "mad",
            "ewma",
            "policy_revision",
        ]
        placeholder = ", ".join("?" for _ in columns)
        with self._connection:
            self._connection.execute(
                f"INSERT OR REPLACE INTO baselines ({', '.join(columns)})"
                f" VALUES ({placeholder})",
                tuple(row[column] for column in columns),
            )

    def fetch_baselines(self, *, status: str | None = None) -> list[sqlite3.Row]:
        statement = "SELECT * FROM baselines"
        parameters: list[Any] = []
        if status is not None:
            statement += " WHERE status = ?"
            parameters.append(status)
        statement += " ORDER BY indicator_id, bucket"
        return list(self._connection.execute(statement, parameters))

    def fetch_baseline(self, indicator_id: str, bucket: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM baselines WHERE indicator_id = ? AND bucket = ?",
            (indicator_id, bucket),
        ).fetchone()

    def latest_eligible_observation(
        self, indicator_id: str, bucket: str
    ) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT observed_at, value FROM observations"
            " WHERE indicator_id = ? AND bucket = ? AND baseline_eligible = 1"
            " ORDER BY observed_at DESC LIMIT 1",
            (indicator_id, bucket),
        ).fetchone()

    def has_deviation_candidate(self, candidate_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM deviation_candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return row is not None

    def insert_deviation_candidates(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = [
            "candidate_id",
            "detected_at",
            "indicator_id",
            "bucket",
            "direction",
            "z_value",
            "ewma_shift",
            "score",
            "policy_revision",
            "policy_digest",
            "baseline_sample_count",
            "limitations_json",
        ]
        placeholder = ", ".join("?" for _ in columns)
        statement = (
            f"INSERT OR IGNORE INTO deviation_candidates ({', '.join(columns)})"
            f" VALUES ({placeholder})"
        )
        with self._connection:
            cursor = self._connection.executemany(
                statement, [tuple(row[column] for column in columns) for row in rows]
            )
        return cursor.rowcount

    def fetch_deviation_candidates(self) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT * FROM deviation_candidates"
                " ORDER BY detected_at, indicator_id, bucket"
            )
        )

    def counts(self) -> dict[str, Any]:
        def scalar(statement: str, parameters: tuple[Any, ...] = ()) -> int:
            row = self._connection.execute(statement, parameters).fetchone()
            return int(row[0])

        modality_counts = {
            str(row["source_modality"]): int(row["n"])
            for row in self._connection.execute(
                "SELECT source_modality, COUNT(*) AS n FROM observations"
                " GROUP BY source_modality"
            )
        }
        span = self._connection.execute(
            "SELECT MIN(observed_at), MAX(observed_at) FROM observations"
        ).fetchone()
        return {
            "ledger_reports": scalar("SELECT COUNT(*) FROM ingest_ledger"),
            "observations": scalar("SELECT COUNT(*) FROM observations"),
            "baseline_eligible_observations": scalar(
                "SELECT COUNT(*) FROM observations WHERE baseline_eligible = 1"
            ),
            "observations_by_modality": modality_counts,
            "episodes": scalar("SELECT COUNT(*) FROM episodes"),
            "baselines_ready": scalar(
                "SELECT COUNT(*) FROM baselines WHERE status = 'ready'"
            ),
            "baselines_insufficient": scalar(
                "SELECT COUNT(*) FROM baselines WHERE status = 'insufficient_samples'"
            ),
            "deviation_candidates": scalar(
                "SELECT COUNT(*) FROM deviation_candidates"
            ),
            "observation_span": {"start": span[0], "end": span[1]},
        }

    def iter_ledger(self) -> Iterator[sqlite3.Row]:
        yield from self._connection.execute(
            "SELECT * FROM ingest_ledger ORDER BY ingested_at"
        )


def dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
