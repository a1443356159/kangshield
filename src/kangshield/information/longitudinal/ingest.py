"""Ingest pipeline reports into the per-elder longitudinal store.

Accepted report shapes (sniffed by top-level keys):
- ``IndicatorExtractionReport`` (video/sleep indicator observations)
- ``FallCandidatePredictionSet`` (L0 fall candidate episodes, clip-relative
  timing only; absolute-time correlation arrives when capture clips carry
  wall-clock references)

Every ingest is idempotent: the source report's sha256 is the ledger key, and
row-level UNIQUE constraints make partial retries safe.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..contracts import (
    FallCandidatePredictionSet,
    IndicatorAssessability,
    IndicatorExtractionReport,
    IndicatorObservation,
    LongitudinalBucket,
    LongitudinalIngestEntry,
    LongitudinalIngestReport,
    utc_now,
)
from ..privacy import sha256_file
from .store import LongitudinalStore, dumps_compact

INGESTOR_VERSION = "longitudinal-ingest-v0.1.0"

# v1 bucket boundaries; mirrored by LongitudinalBaselinePolicy defaults and
# pinned in configs/v1-l1-longitudinal-policy.json.
DAY_START_HOUR = 6
DAY_END_HOUR = 18

CLIP_RELATIVE_TIMING_LIMITATION = "fall_candidate_episode_timing_is_clip_relative_only"


def bucket_for(moment: datetime) -> str:
    if DAY_START_HOUR <= moment.hour < DAY_END_HOUR:
        return LongitudinalBucket.DAY.value
    return LongitudinalBucket.NIGHT.value


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _observation_row(
    observation: IndicatorObservation,
    *,
    report_digest: str,
    run_id: str | None,
    device_ref: str | None,
) -> tuple[dict[str, Any], bool]:
    start_at = observation.time_range.start_at
    tz_aware = start_at is not None and start_at.utcoffset() is not None
    numeric = _numeric_value(observation.value)
    eligible = (
        observation.assessability is IndicatorAssessability.ASSESSABLE
        and numeric is not None
        and tz_aware
    )
    row = {
        "observed_at": start_at.isoformat() if tz_aware else None,
        "bucket": bucket_for(start_at) if tz_aware else None,
        "device_ref": device_ref,
        "indicator_id": observation.indicator_id,
        "group_id": observation.group,
        "source_modality": observation.source_modality,
        "value": numeric,
        "unit": observation.unit,
        "assessability": observation.assessability.value,
        "quality_status": observation.quality_status.value,
        "sample_count": observation.sample_count,
        "scenario_id": observation.scenario_id,
        "time_start_at": start_at.isoformat() if start_at is not None else None,
        "time_end_at": (
            observation.time_range.end_at.isoformat()
            if observation.time_range.end_at is not None
            else None
        ),
        "source_ref": observation.source_ref,
        "run_id": run_id,
        "report_digest": report_digest,
        "limitations_json": dumps_compact(observation.limitations),
        "quality_metrics_json": dumps_compact(observation.quality_metrics),
        "baseline_eligible": 1 if eligible else 0,
    }
    return row, eligible


def _ingest_indicator_extraction(
    payload: dict[str, Any],
    *,
    report_digest: str,
    run_id: str | None,
    device_ref: str | None,
    store: LongitudinalStore,
) -> tuple[int, int]:
    report = IndicatorExtractionReport.model_validate(payload)
    rows: list[dict[str, Any]] = []
    excluded = 0
    for observation in report.observations:
        row, eligible = _observation_row(
            observation,
            report_digest=report_digest,
            run_id=run_id,
            device_ref=device_ref,
        )
        rows.append(row)
        if not eligible:
            excluded += 1
    inserted = store.insert_observations(rows)
    return inserted, excluded


def _ingest_fall_candidate_prediction_set(
    payload: dict[str, Any],
    *,
    report_digest: str,
    device_ref: str | None,
    store: LongitudinalStore,
) -> int:
    prediction_set = FallCandidatePredictionSet.model_validate(payload)
    rows: list[dict[str, Any]] = []
    for clip in prediction_set.clips:
        for candidate in clip.candidates:
            rows.append(
                {
                    "candidate_id": (
                        f"{prediction_set.prediction_set_id}:"
                        f"{clip.scenario_id}:{candidate.candidate_id}"
                    ),
                    "kind": "fall_candidate",
                    "device_ref": device_ref,
                    "start_at": None,
                    "end_at": None,
                    "detected_at": None,
                    "trigger_path": None,
                    "candidate_version": prediction_set.variant_id,
                    "source_ref": f"sha256:{report_digest}",
                    "run_id": prediction_set.source_run_id,
                    "report_digest": report_digest,
                    "payload_json": dumps_compact(
                        {
                            "prediction_set_id": prediction_set.prediction_set_id,
                            "variant_id": prediction_set.variant_id,
                            "scenario_id": clip.scenario_id,
                            "start_ms": candidate.start_ms,
                            "end_ms": candidate.end_ms,
                            "detected_at_ms": candidate.detected_at_ms,
                        }
                    ),
                }
            )
    return store.insert_episodes(rows)


def _sniff_kind(payload: dict[str, Any]) -> str:
    if "extractor_version" in payload:
        return "indicator_extraction"
    if "prediction_set_id" in payload:
        return "fall_candidate_prediction_set"
    raise ValueError("unrecognized longitudinal report shape")


def ingest_report(
    path: Path,
    *,
    elder_ref: str,
    store: LongitudinalStore,
    run_id: str | None = None,
    device_ref: str | None = None,
) -> LongitudinalIngestEntry:
    report_digest = sha256_file(path)
    existing_kind = store.already_ingested(report_digest)
    if existing_kind is not None:
        return LongitudinalIngestEntry(
            report_digest=report_digest,
            report_kind=existing_kind,  # type: ignore[arg-type]
            status="skipped_duplicate",
            run_id=run_id,
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    kind = _sniff_kind(payload)
    observations = 0
    episodes = 0
    excluded = 0
    if kind == "indicator_extraction":
        observations, excluded = _ingest_indicator_extraction(
            payload,
            report_digest=report_digest,
            run_id=run_id,
            device_ref=device_ref,
            store=store,
        )
    else:
        episodes = _ingest_fall_candidate_prediction_set(
            payload,
            report_digest=report_digest,
            device_ref=device_ref,
            store=store,
        )
    store.record_ingest(
        report_digest=report_digest,
        ingested_at=utc_now().isoformat(),
        report_kind=kind,
        run_id=run_id,
        observation_count=observations,
        episode_count=episodes,
    )
    return LongitudinalIngestEntry(
        report_digest=report_digest,
        report_kind=kind,  # type: ignore[arg-type]
        status="ingested",
        run_id=run_id,
        observation_count=observations,
        episode_count=episodes,
        baseline_excluded_count=excluded,
    )


def ingest_reports(
    paths: list[Path],
    *,
    elder_ref: str,
    store: LongitudinalStore,
    run_id: str | None = None,
    device_ref: str | None = None,
) -> LongitudinalIngestReport:
    entries = [
        ingest_report(
            path,
            elder_ref=elder_ref,
            store=store,
            run_id=run_id,
            device_ref=device_ref,
        )
        for path in paths
    ]
    limitations = [CLIP_RELATIVE_TIMING_LIMITATION] if any(
        entry.episode_count > 0 for entry in entries
    ) else []
    return LongitudinalIngestReport(
        ingestor_version=INGESTOR_VERSION,
        elder_ref=elder_ref,
        entries=entries,
        ingested_count=sum(1 for entry in entries if entry.status == "ingested"),
        skipped_duplicate_count=sum(
            1 for entry in entries if entry.status == "skipped_duplicate"
        ),
        limitations=limitations,
    )
