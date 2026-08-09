from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.cli import main
from kangshield.information.contracts import EvidenceLevel, QualityStatus, SourceType
from kangshield.information.event_evaluation import assess_fall_event_evaluation
from kangshield.information.privacy import sha256_file
from scripts.prepare_v1_g4_event_evaluation_fixture import (
    build_event_evaluation_fixture,
)
from scripts.prepare_v1_m2c_timing_fixture import build_fixture


PROJECT_ROOT = Path(__file__).parents[1]
POLICY = PROJECT_ROOT / "configs" / "v1-g4-event-evaluation-policy.json"


def _prepare_bundle(tmp_path: Path) -> Path:
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media = tmp_path / "timing.avi"
    build_fixture(media)
    return build_event_evaluation_fixture(
        tmp_path / "event-evaluation",
        media_source=media,
        project_root=PROJECT_ROOT,
    )


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _refresh(reference: dict, path: Path) -> None:
    reference["sha256"] = sha256_file(path)
    reference["byte_size"] = path.stat().st_size


def test_e1_event_fixture_scores_known_counts_without_risk_or_alert(tmp_path):
    bundle_path = _prepare_bundle(tmp_path)

    assessment = assess_fall_event_evaluation(
        bundle_path,
        policy_path=POLICY,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )

    report = assessment.report
    assert report.decision == "tooling_only"
    assert report.quality_status is QualityStatus.PARTIAL
    assert report.clip_count == 16
    assert report.exposure_ms == 48_000
    assert report.annotation_set_count == 2
    assert report.annotations_complete is True
    assert report.agreement_gate_passed is True
    assert report.adjudication_complete is True
    assert report.minimum_data_gate_passed is True
    assert report.provenance_gate_passed is True
    assert report.capture_camera_gate_passed is False
    assert report.event_metrics_ready_for_review is False
    assert report.ground_truth_event_count == 2
    assert report.negative_clip_count == 14
    assert report.risk_assessment_emitted is False
    assert report.alert_emitted is False

    variants = {variant.variant_id: variant for variant in report.variants}
    rtmpose = variants["rtmpose-m-humanart"]
    assert (rtmpose.true_positive_count, rtmpose.false_positive_count) == (2, 1)
    assert rtmpose.false_negative_count == 0
    assert rtmpose.recall == 1.0
    assert rtmpose.false_activations_per_hour == 75.0
    assert rtmpose.median_detection_delay_ms == 200.0
    assert rtmpose.p95_detection_delay_ms == 290.0

    torchvision = variants["torchvision-keypointrcnn"]
    assert (
        torchvision.true_positive_count,
        torchvision.false_positive_count,
        torchvision.false_negative_count,
    ) == (2, 2, 0)
    assert torchvision.false_activations_per_hour == 150.0
    assert torchvision.median_detection_delay_ms == 100.0

    yolo = variants["yolo26n-pose"]
    assert (
        yolo.true_positive_count,
        yolo.false_positive_count,
        yolo.false_negative_count,
    ) == (1, 1, 1)
    assert yolo.recall == 0.5

    serialized = report.model_dump_json()
    for forbidden in (
        '"start_ms"',
        '"end_ms"',
        '"detected_at_ms"',
        "fixture-independent-annotator",
        "fixture-adjudicator",
        "rtmpose-fp-bed",
        '"relative_path"',
        "camera/C11.synthetic.avi",
    ):
        assert forbidden not in serialized


def test_event_fixture_is_byte_deterministic(tmp_path):
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media = tmp_path / "timing.avi"
    build_fixture(media)
    first = build_event_evaluation_fixture(
        tmp_path / "first",
        media_source=media,
        project_root=PROJECT_ROOT,
    )
    second = build_event_evaluation_fixture(
        tmp_path / "second",
        media_source=media,
        project_root=PROJECT_ROOT,
    )

    first_files = {
        path.relative_to(first.parent): sha256_file(path)
        for path in first.parent.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.parent): sha256_file(path)
        for path in second.parent.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files


def test_event_evaluator_rejects_digest_tampering_without_echoing_path(tmp_path):
    bundle_path = _prepare_bundle(tmp_path)
    bundle = _load(bundle_path)
    bundle["capture_manifest"]["relative_path"] = "../private-person-name.json"
    _write(bundle_path, bundle)

    with pytest.raises(ValueError) as raised:
        assess_fall_event_evaluation(bundle_path, policy_path=POLICY)

    assert "normalized relative path" in str(raised.value)
    assert "private-person-name" not in str(raised.value)


def test_dirty_candidate_source_closes_provenance_gate(tmp_path):
    bundle_path = _prepare_bundle(tmp_path)
    bundle = _load(bundle_path)
    binding = bundle["predictions"][0]
    source_run_path = bundle_path.parent / binding["source_run_manifest"][
        "relative_path"
    ]
    source_run = _load(source_run_path)
    source_run["code_dirty"] = True
    _write(source_run_path, source_run)
    _refresh(binding["source_run_manifest"], source_run_path)
    _write(bundle_path, bundle)

    report = assess_fall_event_evaluation(
        bundle_path,
        policy_path=POLICY,
    ).report

    assert report.provenance_gate_passed is False
    assert report.event_metrics_ready_for_review is False
    assert report.decision == "not_ready"
    assert "candidate_source_provenance_invalid" in {
        issue.code for issue in report.issues
    }
    dirty_variant = next(
        variant
        for variant in report.variants
        if variant.variant_id == binding["variant_id"]
    )
    assert dirty_variant.source_run_clean is False


def test_low_annotation_agreement_closes_gate_but_keeps_aggregate_metrics(tmp_path):
    bundle_path = _prepare_bundle(tmp_path)
    bundle = _load(bundle_path)
    annotation_reference = bundle["annotation_sets"][1]
    annotation_path = bundle_path.parent / annotation_reference["relative_path"]
    annotation = _load(annotation_path)
    for clip in annotation["clips"]:
        if clip["scenario_id"] in {"C11", "C12"}:
            clip["windows"][0]["start_ms"] = 2300
            clip["windows"][0]["end_ms"] = 2900
    _write(annotation_path, annotation)
    _refresh(annotation_reference, annotation_path)

    annotation_digests = sorted(
        reference["sha256"] for reference in bundle["annotation_sets"]
    )
    adjudication_path = bundle_path.parent / bundle["adjudication"][
        "relative_path"
    ]
    adjudication = _load(adjudication_path)
    adjudication["input_annotation_sha256s"] = annotation_digests
    _write(adjudication_path, adjudication)
    _refresh(bundle["adjudication"], adjudication_path)
    _write(bundle_path, bundle)

    report = assess_fall_event_evaluation(
        bundle_path,
        policy_path=POLICY,
    ).report

    assert report.annotations_complete is True
    assert report.agreement_gate_passed is False
    assert report.annotation_agreements[0].target_interval_f1 == 0.0
    assert report.decision == "not_ready"
    assert len(report.variants) == 3
    assert all(variant.ground_truth_event_count == 2 for variant in report.variants)


def test_cli_require_ready_returns_two_after_completed_fixture_assessment(
    tmp_path,
    capsys,
):
    bundle_path = _prepare_bundle(tmp_path)
    runs_dir = tmp_path / "runs"

    exit_code = main(
        [
            "assess-event-evaluation",
            str(bundle_path),
            "--policy",
            str(POLICY),
            "--runs-dir",
            str(runs_dir),
            "--require-ready",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    run_manifest = _load(Path(output["manifest"]))

    assert exit_code == 2
    assert output["decision"] == "tooling_only"
    assert output["event_metrics_ready_for_review"] is False
    assert run_manifest["status"] == "completed"
    assert run_manifest["configuration"]["input_paths_persisted"] is False
    assert (
        Path(output["manifest"]).parent
        / "reports"
        / "g4-event-evaluation-readiness.json"
    ).is_file()
