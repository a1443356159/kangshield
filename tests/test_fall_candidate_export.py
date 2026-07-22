from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kangshield.information.cli import main
from kangshield.information.contracts import (
    EvidenceLevel,
    FallCandidateExportSummary,
    FallCandidatePredictionSet,
    FallFeatureClipStream,
    RunManifest,
    SourceType,
)
from kangshield.information.event_evaluation import assess_fall_event_evaluation
from kangshield.information.fall_candidate_export import run_fall_candidate_export
from kangshield.information.privacy import sha256_file
from scripts.prepare_v1_g4_candidate_export_fixture import (
    build_candidate_export_fixture,
)
from scripts.prepare_v1_m2c_timing_fixture import build_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_POLICY = PROJECT_ROOT / "configs" / "v1-g4-event-evaluation-policy.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_feature_stream_contract_rejects_parent_traversal():
    with pytest.raises(ValidationError, match="normalized and relative"):
        FallFeatureClipStream(
            scenario_id="C01",
            duration_ms=3000,
            observation_id="observation-C01",
            relative_path="../private/features.jsonl",
            sha256="0" * 64,
            byte_size=1,
            frame_count=1,
        )


def test_rule_bearing_export_is_directly_consumable_by_event_evaluator(
    tmp_path: Path,
    capsys,
):
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media_path = tmp_path / "timing.avi"
    build_fixture(media_path)
    bundle_path = build_candidate_export_fixture(
        tmp_path / "candidate-export",
        media_source=media_path,
        project_root=PROJECT_ROOT,
    )
    bundle_root = bundle_path.parent
    bundle = _load(bundle_path)

    assessment = assess_fall_event_evaluation(
        bundle_path,
        policy_path=EVENT_POLICY,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )
    assert assessment.report.clip_count == 12
    assert assessment.report.ground_truth_event_count == 2
    assert assessment.report.risk_assessment_emitted is False
    assert assessment.report.alert_emitted is False
    observed_counts = {
        variant.variant_id: variant.candidate_event_count
        for variant in assessment.report.variants
    }
    assert observed_counts == {
        "rtmpose-m-humanart": 3,
        "torchvision-keypointrcnn": 4,
        "yolo26n-pose": 2,
    }

    for binding in bundle["predictions"]:
        prediction_path = bundle_root / binding["candidate_events"]["relative_path"]
        source_run_path = (
            bundle_root / binding["source_run_manifest"]["relative_path"]
        )
        prediction = FallCandidatePredictionSet.model_validate_json(
            prediction_path.read_text(encoding="utf-8")
        )
        source_run = RunManifest.model_validate_json(
            source_run_path.read_text(encoding="utf-8")
        )
        summary = FallCandidateExportSummary.model_validate_json(
            (source_run_path.parent / "reports" / "fall-candidate-export-summary.json")
            .read_text(encoding="utf-8")
        )
        assert prediction.source_run_id == source_run.run_id
        assert source_run.configuration["candidate_events_sha256"] == sha256_file(
            prediction_path
        )
        assert summary.candidate_events_sha256 == sha256_file(prediction_path)
        serialized_summary = summary.model_dump_json()
        assert "generated_at" not in serialized_summary
        assert str(tmp_path) not in serialized_summary

    variant_id = "yolo26n-pose"
    feature_run_dir = (
        bundle_root / "feature-runs" / f"fixture-features-{variant_id}"
    )
    exit_code = main(
        [
            "export-fall-candidates",
            str(bundle_root / "capture" / "capture-manifest.json"),
            str(feature_run_dir / "reports" / "fall-feature-capture-set.json"),
            str(feature_run_dir / "manifest.json"),
            "--policy",
            str(bundle_root / "policies" / "candidate-policy.json"),
            "--runs-dir",
            str(tmp_path / "cli-runs"),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["variant_id"] == variant_id
    assert output["clip_count"] == 12
    assert output["candidate_episode_count"] == 2
    assert output["risk_assessment_emitted"] is False
    assert output["alert_emitted"] is False

    stream_path = feature_run_dir / "artifacts" / "C01.jsonl"
    stream_path.write_text(
        stream_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="byte size differs"):
        run_fall_candidate_export(
            capture_manifest_path=(
                bundle_root / "capture" / "capture-manifest.json"
            ),
            feature_set_path=(
                feature_run_dir / "reports" / "fall-feature-capture-set.json"
            ),
            source_feature_run_manifest_path=feature_run_dir / "manifest.json",
            policy_path=bundle_root / "policies" / "candidate-policy.json",
            runs_dir=tmp_path / "tampered-runs",
            evidence_level=EvidenceLevel.E1,
        )
