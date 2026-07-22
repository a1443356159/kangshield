from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.contracts import (
    EvidenceLevel,
    QualityStatus,
    SourceType,
)
from kangshield.information.m2c_capture import assess_m2c_capture
from kangshield.information.privacy import sha256_file
from scripts.prepare_v1_m2c_capture_fixture import build_capture_fixture
from scripts.prepare_v1_m2c_timing_fixture import build_fixture


PROJECT_ROOT = Path(__file__).parents[1]
POLICY = PROJECT_ROOT / "configs" / "v1-m2c-capture-policy.json"


def _prepare_bundle(tmp_path: Path) -> Path:
    pytest.importorskip("av")
    pytest.importorskip("numpy")
    media = tmp_path / "timing.avi"
    build_fixture(media)
    return build_capture_fixture(
        tmp_path / "capture",
        media_source=media,
        project_root=PROJECT_ROOT,
    )


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _refresh_reference(reference: dict, path: Path) -> None:
    reference["sha256"] = sha256_file(path)
    if "byte_size" in reference:
        reference["byte_size"] = path.stat().st_size


def test_e1_capture_fixture_exercises_full_structure_without_device_claim(tmp_path):
    manifest_path = _prepare_bundle(tmp_path)

    assessment = assess_m2c_capture(
        manifest_path,
        policy_path=POLICY,
        evidence_level=EvidenceLevel.E1,
        source_type=SourceType.FIXTURE,
    )

    report = assessment.report
    assert report.decision == "tooling_only"
    assert report.quality_status is QualityStatus.PARTIAL
    assert report.counts["declared_clip_count"] == 10
    assert report.counts["usable_clip_count"] == 10
    assert report.counts["synchronized_usable_clip_count"] == 1
    assert report.counts["error_count"] == 0
    assert report.coverage["missing_core_tags"] == []
    assert report.coverage["missing_full_matrix_scenario_ids"] == []
    assert report.camera_ready_for_model_retest is False
    assert report.camera_matrix_complete is False
    assert report.sleep_sample_ready_for_profiling is False
    assert report.m2c_ready_for_review is False
    assert len(assessment.media_reports) == 10
    assert len(assessment.sleep_assets) == 1

    serialized = report.model_dump_json()
    assert "fixture-operator" not in serialized
    assert "fixture-no-human" not in serialized
    assert "C01.synthetic.avi" not in serialized
    assert '"start_ms"' not in serialized
    assert "camera/" not in serialized


def test_capture_gate_blocks_path_escape_and_does_not_echo_it(tmp_path):
    manifest_path = _prepare_bundle(tmp_path)
    manifest = _load_manifest(manifest_path)
    manifest["clips"][0]["relative_path"] = "../outside-private-name.avi"
    _write_manifest(manifest_path, manifest)

    report = assess_m2c_capture(
        manifest_path,
        policy_path=POLICY,
    ).report

    c01 = next(clip for clip in report.clips if clip.scenario_id == "C01")
    assert c01.usable_for_model_retest is False
    assert "bundle_path_invalid" in {issue.code for issue in c01.issues}
    assert report.decision == "not_ready"
    assert "outside-private-name" not in report.model_dump_json()


def test_capture_gate_blocks_digest_tampering(tmp_path):
    manifest_path = _prepare_bundle(tmp_path)
    manifest = _load_manifest(manifest_path)
    manifest["clips"][4]["sha256"] = "f" * 64
    _write_manifest(manifest_path, manifest)

    report = assess_m2c_capture(
        manifest_path,
        policy_path=POLICY,
    ).report

    c05 = next(clip for clip in report.clips if clip.scenario_id == "C05")
    assert c05.manifest_digest_match is False
    assert c05.usable_for_model_retest is False
    assert report.counts["usable_clip_count"] == 9
    assert "media_sha256_mismatch" in {issue.code for issue in c05.issues}


def test_e2_complete_bundle_opens_review_gate_only_after_fixture_markers_removed(
    tmp_path,
):
    manifest_path = _prepare_bundle(tmp_path)
    root = manifest_path.parent
    manifest = _load_manifest(manifest_path)
    manifest["synthetic"] = False
    manifest["operator_ref"] = "consented-operator-ref"
    manifest["participant_ref"] = "consented-participant-ref"

    consent_path = root / manifest["consent"]["relative_path"]
    consent_path.write_text('{"consent_recorded": true}\n', encoding="utf-8")
    _refresh_reference(manifest["consent"], consent_path)
    for device in manifest["devices"]:
        device["acquisition_method"] = (
            "playback_export"
            if device["model"] == "CS-C6c-V101-1J4WF"
            else "app_export"
        )
        capability = root / device["capability_snapshot"]["relative_path"]
        capability.write_text(
            json.dumps({"model": device["model"], "observed": True}) + "\n",
            encoding="utf-8",
        )
        _refresh_reference(device["capability_snapshot"], capability)

    for index, clip in enumerate(manifest["clips"]):
        media = root / clip["relative_path"]
        with media.open("ab") as stream:
            stream.write(b"KS" + index.to_bytes(2, "big"))
        _refresh_reference(clip, media)
        for event in clip["synchronization_events"]:
            event["annotation_method"] = "manual_frame_and_waveform"

    sleep_export = manifest["sleep_exports"][0]
    sleep_path = root / sleep_export["relative_path"]
    sleep_path.write_text('{"records": []}\n', encoding="utf-8")
    _refresh_reference(sleep_export, sleep_path)
    _write_manifest(manifest_path, manifest)

    report = assess_m2c_capture(
        manifest_path,
        policy_path=POLICY,
        evidence_level=EvidenceLevel.E2,
        source_type=SourceType.LOCAL_FILE,
    ).report

    assert report.decision == "ready_for_review"
    assert report.quality_status is QualityStatus.PASS
    assert report.camera_ready_for_model_retest is True
    assert report.camera_matrix_complete is True
    assert report.sleep_sample_ready_for_profiling is True
    assert report.m2c_ready_for_review is True
    assert report.counts["duplicate_media_content_count"] == 0
    assert report.counts["error_count"] == 0
