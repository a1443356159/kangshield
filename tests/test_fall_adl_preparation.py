from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.artifacts import atomic_write_json
from kangshield.information.fall_adl_preparation import (
    load_fall_adl_source_manifest,
    prepare_v1_g4_caucafall_data,
)
from kangshield.information.privacy import sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = PROJECT_ROOT / "configs" / "v1-g4-caucafall-negative-videos.json"


def _tiny_video(path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 48)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MJPG video writer unavailable")
    for value in range(4):
        writer.write(np.full((48, 64, 3), value * 20, dtype=np.uint8))
    writer.release()


def test_caucafall_source_manifest_freezes_matrix_and_provenance():
    manifest = load_fall_adl_source_manifest(SOURCE_MANIFEST)

    assert manifest["suite_id"] == "v1-g4-caucafall-adl-negative-12"
    assert manifest["dataset"]["license"] == "CC-BY-4.0"
    assert len(manifest["cases"]) == 12
    assert {item["subject_ref"] for item in manifest["cases"]} == {
        "subject-01",
        "subject-06",
        "subject-10",
    }
    assert len({item["file_id"] for item in manifest["cases"]}) == 12


def test_caucafall_source_manifest_rejects_license_and_matrix_drift(tmp_path):
    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    payload["dataset"]["license"] = "unknown"
    drifted = tmp_path / "drifted.json"
    atomic_write_json(drifted, payload)
    with pytest.raises(ValueError, match="license is not the frozen value"):
        load_fall_adl_source_manifest(drifted)

    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    payload["cases"].pop()
    atomic_write_json(drifted, payload)
    with pytest.raises(ValueError, match="complete subject/activity matrix"):
        load_fall_adl_source_manifest(drifted)


def test_prepare_caucafall_verifies_and_writes_deterministic_lock(
    tmp_path, monkeypatch
):
    video_source = tmp_path / "source.avi"
    _tiny_video(video_source)
    video_bytes = video_source.read_bytes()
    video_digest = sha256_file(video_source)
    metadata_bytes = b"frozen dataset details fixture"
    metadata_path = tmp_path / "details.xlsx"
    metadata_path.write_bytes(metadata_bytes)
    metadata_digest = sha256_file(metadata_path)

    payload = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    payload["provenance_files"][0]["byte_size"] = len(metadata_bytes)
    payload["provenance_files"][0]["sha256"] = metadata_digest
    for case in payload["cases"]:
        case["byte_size"] = len(video_bytes)
        case["sha256"] = video_digest
    manifest_path = tmp_path / "source-manifest.json"
    atomic_write_json(manifest_path, payload)

    def fake_download(url, target, *, byte_size, sha256):
        del url
        content = metadata_bytes if sha256 == metadata_digest else video_bytes
        assert len(content) == byte_size
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        assert sha256_file(target) == sha256

    monkeypatch.setattr(
        "kangshield.information.fall_adl_preparation.download_and_verify",
        fake_download,
    )
    first = prepare_v1_g4_caucafall_data(
        manifest_path=manifest_path,
        download_dir=tmp_path / "downloads-one",
        output_dir=tmp_path / "processed-one",
    )
    second = prepare_v1_g4_caucafall_data(
        manifest_path=manifest_path,
        download_dir=tmp_path / "downloads-two",
        output_dir=tmp_path / "processed-two",
    )

    first_suite = Path(first["fall_adl_cases"])
    second_suite = Path(second["fall_adl_cases"])
    assert first["case_count"] == 12
    assert first["source_file_count"] == 13
    assert sha256_file(first_suite) == sha256_file(second_suite)
    assert Path(first["dataset_lock"]).read_bytes() == Path(
        second["dataset_lock"]
    ).read_bytes()
    suite = json.loads(first_suite.read_text(encoding="utf-8"))
    assert suite["case_count"] == 12
    assert all(
        (first_suite.parent / item["video_path"]).is_file()
        for item in suite["cases"]
    )
