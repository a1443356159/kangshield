from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from kangshield.information.cli import main
from kangshield.information.contracts import EvidenceLevel, SourceType
from kangshield.information.event_bundle import (
    assemble_fall_event_evaluation_bundle,
)
from kangshield.information.event_evaluation import assess_fall_event_evaluation
from scripts.prepare_v1_g4_event_evaluation_fixture import (
    build_event_evaluation_fixture,
)
from scripts.prepare_v1_m2c_timing_fixture import build_fixture


PROJECT_ROOT = Path(__file__).parents[1]
EVALUATION_POLICY = (
    PROJECT_ROOT / "configs" / "v1-g4-event-evaluation-policy.json"
)


def _prepare_sources(tmp_path: Path) -> tuple[Path, dict]:
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media = tmp_path / "timing.avi"
    build_fixture(media)
    bundle_path = build_event_evaluation_fixture(
        tmp_path / "source",
        media_source=media,
        project_root=PROJECT_ROOT,
    )
    return bundle_path, json.loads(bundle_path.read_text(encoding="utf-8"))


def _path(root: Path, reference: dict) -> Path:
    return root / reference["relative_path"]


def _assemble(tmp_path: Path):
    source_bundle_path, source_bundle = _prepare_sources(tmp_path)
    root = source_bundle_path.parent
    return assemble_fall_event_evaluation_bundle(
        output_dir=tmp_path / "assembled",
        capture_manifest_path=_path(root, source_bundle["capture_manifest"]),
        capture_readiness_report_path=_path(
            root,
            source_bundle["capture_readiness_report"],
        ),
        capture_assessment_run_manifest_path=_path(
            root,
            source_bundle["capture_assessment_run_manifest"],
        ),
        candidate_policy_path=_path(
            root,
            source_bundle["candidate_generator_policy"],
        ),
        annotation_paths=[
            _path(root, reference)
            for reference in source_bundle["annotation_sets"]
        ],
        adjudication_path=_path(root, source_bundle["adjudication"]),
        prediction_sources=[
            (
                _path(root, binding["candidate_events"]),
                _path(root, binding["source_run_manifest"]),
            )
            for binding in source_bundle["predictions"]
        ],
        evaluation_policy_path=EVALUATION_POLICY,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )


def test_event_bundle_assembler_publishes_self_contained_private_preflight(
    tmp_path,
):
    assembly = _assemble(tmp_path)

    assert assembly.report.preflight_decision == "tooling_only"
    assert assembly.report.provenance_gate_passed is True
    assert assembly.report.event_metrics_ready_for_review is False
    assert assembly.report.variant_ids == [
        "rtmpose-m-humanart",
        "torchvision-keypointrcnn",
        "yolo26n-pose",
    ]
    assert assembly.report.annotation_set_count == 2
    assert assembly.report.copied_source_file_count == 13
    assert assembly.report.raw_media_copied is False
    assert assembly.report.risk_assessment_emitted is False
    assert assembly.report.alert_emitted is False

    payload = assembly.bundle_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in payload
    assert ".." not in payload
    bundled = json.loads(payload)
    referenced = [
        bundled["capture_manifest"],
        bundled["capture_readiness_report"],
        bundled["capture_assessment_run_manifest"],
        bundled["candidate_generator_policy"],
        *bundled["annotation_sets"],
        bundled["adjudication"],
        *(
            reference
            for binding in bundled["predictions"]
            for reference in (
                binding["candidate_events"],
                binding["source_run_manifest"],
            )
        ),
    ]
    assert all(
        stat.S_IMODE((assembly.bundle_path.parent / item["relative_path"]).stat().st_mode)
        == 0o600
        for item in referenced
    )

    reassessed = assess_fall_event_evaluation(
        assembly.bundle_path,
        policy_path=EVALUATION_POLICY,
    ).report
    assert reassessed.model_dump(mode="json") == assembly.preflight.model_dump(
        mode="json"
    )


def test_event_bundle_assembler_removes_staging_after_failed_preflight(tmp_path):
    source_bundle_path, source_bundle = _prepare_sources(tmp_path)
    root = source_bundle_path.parent
    annotation_path = _path(root, source_bundle["annotation_sets"][0])
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    annotation["capture_manifest_sha256"] = "0" * 64
    annotation_path.write_text(
        json.dumps(annotation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "invalid-output"

    with pytest.raises(ValueError, match="another capture manifest"):
        assemble_fall_event_evaluation_bundle(
            output_dir=output,
            capture_manifest_path=_path(
                root,
                source_bundle["capture_manifest"],
            ),
            capture_readiness_report_path=_path(
                root,
                source_bundle["capture_readiness_report"],
            ),
            capture_assessment_run_manifest_path=_path(
                root,
                source_bundle["capture_assessment_run_manifest"],
            ),
            candidate_policy_path=_path(
                root,
                source_bundle["candidate_generator_policy"],
            ),
            annotation_paths=[
                _path(root, reference)
                for reference in source_bundle["annotation_sets"]
            ],
            adjudication_path=_path(root, source_bundle["adjudication"]),
            prediction_sources=[
                (
                    _path(root, item["candidate_events"]),
                    _path(root, item["source_run_manifest"]),
                )
                for item in source_bundle["predictions"]
            ],
            evaluation_policy_path=EVALUATION_POLICY,
        )

    assert not output.exists()
    assert not list(tmp_path.glob(".invalid-output.*"))


def test_event_bundle_cli_wires_repeated_annotations_and_variants(
    tmp_path,
    capsys,
):
    source_bundle_path, source_bundle = _prepare_sources(tmp_path)
    root = source_bundle_path.parent
    output = tmp_path / "cli-output"
    arguments = [
        "assemble-event-evaluation-bundle",
        str(_path(root, source_bundle["capture_manifest"])),
        str(_path(root, source_bundle["capture_readiness_report"])),
        str(_path(root, source_bundle["capture_assessment_run_manifest"])),
        str(_path(root, source_bundle["candidate_generator_policy"])),
        str(_path(root, source_bundle["adjudication"])),
    ]
    for reference in source_bundle["annotation_sets"]:
        arguments.extend(("--annotation", str(_path(root, reference))))
    for binding in source_bundle["predictions"]:
        arguments.extend(
            (
                "--prediction-source",
                str(_path(root, binding["candidate_events"])),
                str(_path(root, binding["source_run_manifest"])),
            )
        )
    arguments.extend(
        (
            "--evaluation-policy",
            str(EVALUATION_POLICY),
            "--output",
            str(output),
        )
    )

    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["bundle"]).is_file()
    assert result["preflight_decision"] == "tooling_only"
    assert result["provenance_gate_passed"] is True
    assert result["event_metrics_ready_for_review"] is False
    assert result["risk_assessment_emitted"] is False
    assert result["alert_emitted"] is False
