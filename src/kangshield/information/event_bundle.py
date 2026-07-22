from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from .artifacts import atomic_write_json
from .contracts import (
    EvidenceLevel,
    FallCandidatePredictionSet,
    FallEventBundleAssemblyReport,
    FallEventCandidatePolicy,
    FallEventEvaluationReadinessReport,
    RunManifest,
    SourceType,
    ensure_source_evidence_compatible,
)
from .event_evaluation import assess_fall_event_evaluation
from .m2c_capture import load_m2c_event_context
from .privacy import sha256_file


EVENT_BUNDLE_ASSEMBLER_VERSION = "g4-event-bundle-assembler-v0.1.0"
_SAFE_VARIANT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class FallEventBundleAssembly:
    bundle_path: Path
    preflight_path: Path
    assembly_report_path: Path
    report: FallEventBundleAssemblyReport
    preflight: FallEventEvaluationReadinessReport


def _load_json(path: Path, model, *, kind: str):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{kind} could not be read as JSON") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"{kind} schema validation failed") from error


def _copy_private(source: Path, destination: Path) -> Path:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError("event bundle source file not found")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    return destination


def _reference(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
    }


def _publish_staging(staging: Path, output_dir: Path) -> None:
    if output_dir.exists():
        raise FileExistsError("event bundle output already exists")
    staging.replace(output_dir)


def assemble_fall_event_evaluation_bundle(
    *,
    output_dir: Path,
    capture_manifest_path: Path,
    capture_readiness_report_path: Path,
    capture_assessment_run_manifest_path: Path,
    candidate_policy_path: Path,
    annotation_paths: Iterable[Path],
    adjudication_path: Path,
    prediction_sources: Iterable[tuple[Path, Path]],
    evaluation_policy_path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    source_type: SourceType = SourceType.FIXTURE,
    evaluation_id: str | None = None,
    limitations: Iterable[str] = (),
) -> FallEventBundleAssembly:
    """Copy verified inputs into a private, self-contained evaluator bundle."""

    ensure_source_evidence_compatible(source_type, evidence_level)
    annotations = [Path(path).resolve() for path in annotation_paths]
    predictions = [
        (Path(prediction).resolve(), Path(manifest).resolve())
        for prediction, manifest in prediction_sources
    ]
    if len(annotations) < 2:
        raise ValueError("event bundle assembly requires two annotation sets")
    if not predictions:
        raise ValueError("event bundle assembly requires candidate predictions")

    capture_manifest_path = Path(capture_manifest_path).resolve()
    capture_readiness_report_path = Path(capture_readiness_report_path).resolve()
    capture_assessment_run_manifest_path = Path(
        capture_assessment_run_manifest_path
    ).resolve()
    candidate_policy_path = Path(candidate_policy_path).resolve()
    adjudication_path = Path(adjudication_path).resolve()
    evaluation_policy_path = Path(evaluation_policy_path).resolve()
    required_files = (
        capture_manifest_path,
        capture_readiness_report_path,
        capture_assessment_run_manifest_path,
        candidate_policy_path,
        adjudication_path,
        evaluation_policy_path,
        *annotations,
        *(path for pair in predictions for path in pair),
    )
    if any(not path.is_file() for path in required_files):
        raise FileNotFoundError("an event bundle input file is missing")
    annotations.sort(key=sha256_file)

    context = load_m2c_event_context(capture_manifest_path)
    candidate_policy = _load_json(
        candidate_policy_path,
        FallEventCandidatePolicy,
        kind="candidate generator policy",
    )
    fixture = source_type is SourceType.FIXTURE
    if fixture != context.synthetic or fixture != candidate_policy.fixture:
        raise ValueError("event bundle fixture markers disagree")

    loaded_predictions: list[tuple[FallCandidatePredictionSet, RunManifest]] = []
    for prediction_path, source_run_path in predictions:
        prediction = _load_json(
            prediction_path,
            FallCandidatePredictionSet,
            kind="candidate prediction",
        )
        source_run = _load_json(
            source_run_path,
            RunManifest,
            kind="candidate source run",
        )
        if prediction.source_run_id != source_run.run_id:
            raise ValueError("candidate prediction source run id disagrees")
        if not _SAFE_VARIANT.fullmatch(prediction.variant_id):
            raise ValueError("candidate prediction variant id is not filename-safe")
        loaded_predictions.append((prediction, source_run))
    variants = [prediction.variant_id for prediction, _ in loaded_predictions]
    if len(variants) != len(set(variants)):
        raise ValueError("event bundle candidate variants must be unique")

    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError("event bundle output already exists")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name or 'event-bundle'}.",
            dir=output_dir.parent,
        )
    )
    try:
        capture_copy = _copy_private(
            capture_manifest_path,
            staging / "capture" / "capture-manifest.json",
        )
        readiness_copy = _copy_private(
            capture_readiness_report_path,
            staging / "evidence" / "m2c-capture-readiness.json",
        )
        capture_run_copy = _copy_private(
            capture_assessment_run_manifest_path,
            staging / "evidence" / "m2c-capture-run-manifest.json",
        )
        candidate_policy_copy = _copy_private(
            candidate_policy_path,
            staging / "policies" / "candidate-policy.json",
        )
        annotation_copies = [
            _copy_private(
                path,
                staging / "annotations" / f"annotation-{index:03d}.json",
            )
            for index, path in enumerate(annotations, start=1)
        ]
        adjudication_copy = _copy_private(
            adjudication_path,
            staging / "annotations" / "adjudication.json",
        )
        prediction_bindings = []
        for (prediction_path, source_run_path), (prediction, _) in zip(
            predictions,
            loaded_predictions,
            strict=True,
        ):
            prediction_copy = _copy_private(
                prediction_path,
                staging / "predictions" / f"{prediction.variant_id}.json",
            )
            run_copy = _copy_private(
                source_run_path,
                staging
                / "source-runs"
                / f"{prediction.variant_id}.manifest.json",
            )
            prediction_bindings.append(
                {
                    "variant_id": prediction.variant_id,
                    "candidate_events": _reference(prediction_copy, staging),
                    "source_run_manifest": _reference(run_copy, staging),
                }
            )

        bundle_path = staging / "event-evaluation-bundle.json"
        bundle_payload = {
            "schema_version": "1.0",
            "evaluation_id": evaluation_id
            or f"v1-g4-event-{context.capture_ref.removeprefix('capture_')}",
            "fixture": fixture,
            "capture_manifest": _reference(capture_copy, staging),
            "capture_readiness_report": _reference(readiness_copy, staging),
            "capture_assessment_run_manifest": _reference(
                capture_run_copy,
                staging,
            ),
            "candidate_generator_policy": _reference(
                candidate_policy_copy,
                staging,
            ),
            "annotation_sets": [
                _reference(path, staging) for path in annotation_copies
            ],
            "adjudication": _reference(adjudication_copy, staging),
            "predictions": sorted(
                prediction_bindings,
                key=lambda item: item["variant_id"],
            ),
            "limitations": [
                *limitations,
                "bundle_contains_derived_sensitive_annotations_and_predictions",
                "bundle_assembly_does_not_generate_risk_or_alert",
            ],
        }
        atomic_write_json(bundle_path, bundle_payload)
        bundle_path.chmod(0o600)
        preflight = assess_fall_event_evaluation(
            bundle_path,
            policy_path=evaluation_policy_path,
            evidence_level=evidence_level,
            source_type=source_type,
        ).report
        preflight_path = staging / "event-evaluation-preflight.json"
        atomic_write_json(preflight_path, preflight)
        preflight_path.chmod(0o600)
        assembly_report = FallEventBundleAssemblyReport(
            assembler_version=EVENT_BUNDLE_ASSEMBLER_VERSION,
            bundle_sha256=sha256_file(bundle_path),
            fixture=fixture,
            evidence_level=evidence_level,
            source_type=source_type,
            capture_manifest_sha256=context.manifest_sha256,
            candidate_generator_policy_sha256=sha256_file(
                candidate_policy_copy
            ),
            annotation_set_count=len(annotation_copies),
            variant_ids=sorted(variants),
            copied_source_file_count=(
                5 + len(annotation_copies) + 2 * len(prediction_bindings)
            ),
            preflight_decision=preflight.decision,
            preflight_quality_status=preflight.quality_status,
            provenance_gate_passed=preflight.provenance_gate_passed,
            event_metrics_ready_for_review=(
                preflight.event_metrics_ready_for_review
            ),
            limitations=[
                "assembly_preflight_does_not_authorize_risk_or_alert",
                "source_media_remains_in_the_original_capture_store",
            ],
        )
        assembly_report_path = staging / "bundle-assembly-report.json"
        atomic_write_json(assembly_report_path, assembly_report)
        assembly_report_path.chmod(0o600)
        _publish_staging(staging, output_dir)
        return FallEventBundleAssembly(
            bundle_path=output_dir / bundle_path.name,
            preflight_path=output_dir / preflight_path.name,
            assembly_report_path=output_dir / assembly_report_path.name,
            report=assembly_report,
            preflight=preflight,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
