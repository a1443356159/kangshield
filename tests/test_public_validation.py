from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kangshield.validation.caucafall import (
    CAUCAFALL_ACTIVITIES,
    CAUCAFALL_DEV_SUBJECTS,
    CAUCAFALL_HOLDOUT_SUBJECTS,
    CaucafallCase,
    PublicValidationError,
    aggregate_metrics,
    cases_for_split,
    download_case,
    evaluate_engineering_gate,
    main,
    parse_activity_files,
    parse_folder_tree,
)


def _case(subject: int, activity: str = "Fall forward") -> CaucafallCase:
    content = f"subject={subject};activity={activity}".encode()
    return CaucafallCase(
        subject=subject,
        activity=activity,
        label="fall" if activity.startswith("Fall ") else "adl",
        folder_id=f"activity-{subject}-{activity}",
        file_id=f"file-{subject}-{activity}",
        filename=f"S{subject}-{activity}.avi",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        download_url="https://data.mendeley.com/public-files/example/file_downloaded",
    )


def test_folder_tree_is_subject_isolated_and_complete():
    payload = []
    for subject in range(1, 11):
        parent = f"subject-{subject}"
        payload.append({"id": parent, "name": f"Subject.{subject}"})
        for index, activity in enumerate(CAUCAFALL_ACTIVITIES):
            payload.append(
                {
                    "id": f"activity-{subject}-{index}",
                    "name": activity,
                    "parent_id": parent,
                }
            )

    parsed = parse_folder_tree(payload)

    assert len(parsed) == 100
    assert parsed[0] == (1, "Fall backwards", "activity-1-0")
    assert parsed[-1] == (10, "Walk", "activity-10-9")


def test_activity_files_selects_only_the_official_avi():
    content = b"video"
    payload = [
        {"filename": "frame.png", "id": "png", "content_details": {}},
        {
            "filename": "FallForwardS1.avi",
            "id": "avi-id",
            "content_details": {
                "size": len(content),
                "sha256_hash": hashlib.sha256(content).hexdigest(),
                "download_url": "https://data.mendeley.com/public-files/x/file_downloaded",
            },
        },
    ]

    case = parse_activity_files(
        payload, subject=1, activity="Fall forward", folder_id="folder"
    )

    assert case.label == "fall"
    assert case.filename == "FallForwardS1.avi"
    assert "download_url" not in case.public_manifest()["source_file"]


def test_dev_and_holdout_subjects_never_overlap():
    cases = [_case(subject) for subject in range(1, 11)]

    dev = cases_for_split(cases, "dev")
    holdout = cases_for_split(cases, "holdout")

    assert {item.subject for item in dev} == set(CAUCAFALL_DEV_SUBJECTS)
    assert {item.subject for item in holdout} == set(CAUCAFALL_HOLDOUT_SUBJECTS)
    assert {item.case_ref for item in dev}.isdisjoint(
        item.case_ref for item in holdout
    )


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_download_is_atomic_private_and_hash_verified(tmp_path):
    case = _case(1)
    content = b"subject=1;activity=Fall forward"

    path = download_case(
        case,
        tmp_path,
        opener=lambda request, timeout: _Response(content),
    )

    assert path.read_bytes() == content
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.rglob("*.part-*"))

    bad = _case(2)
    with pytest.raises(PublicValidationError, match="integrity mismatch"):
        download_case(
            bad,
            tmp_path,
            opener=lambda request, timeout: _Response(b"tampered"),
        )


def test_metrics_are_clip_level_and_keep_gate_cost_visible():
    rows = [
        {
            "label": "fall",
            "gated": {
                "candidate_count": 1,
                "candidate_detected_at_ms": [800],
                "pose_person_coverage": 0.8,
                "motion_retained": True,
                "selection_ratio": 0.4,
            },
        },
        {
            "label": "fall",
            "gated": {
                "candidate_count": 0,
                "candidate_detected_at_ms": [],
                "pose_person_coverage": 0.6,
                "motion_retained": False,
                "selection_ratio": 0.2,
            },
        },
        {
            "label": "adl",
            "gated": {
                "candidate_count": 1,
                "candidate_detected_at_ms": [900],
                "pose_person_coverage": 0.7,
                "motion_retained": True,
                "selection_ratio": 0.3,
            },
        },
    ]

    metrics = aggregate_metrics(rows)["gated"]

    assert metrics["fall_event_recall"] == 0.5
    assert metrics["adl_clip_false_positive_rate"] == 1.0
    assert metrics["fall_motion_gate_retention"] == 0.5
    assert metrics["mean_selected_frame_ratio"] == 0.3


def test_prepare_only_verifies_media_without_loading_pose_model(tmp_path, capsys):
    case = _case(1)
    cached = tmp_path / "cached.avi"
    cached.write_bytes(b"video")

    with (
        patch("kangshield.validation.caucafall.load_catalog", return_value=[case]),
        patch("kangshield.validation.caucafall.download_case", return_value=cached),
        patch(
            "kangshield.validation.caucafall.UltralyticsPoseBackend",
            side_effect=AssertionError("prepare-only must not load a model"),
        ),
    ):
        result = main(
            [
                "--split",
                "dev",
                "--cache-root",
                str(tmp_path),
                "--accept-license",
                "CC-BY-4.0",
                "--prepare-only",
            ]
        )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["verified_clip_count"] == 1
    assert payload["model_loaded"] is False


def test_engineering_gate_is_explicit_and_fail_closed():
    passing = evaluate_engineering_gate(
        {
            "gated": {
                "fall_event_recall": 0.52,
                "adl_clip_false_positive_rate": 0.08,
                "fall_motion_gate_retention": 0.96,
                "mean_selected_frame_ratio": 0.5,
                "mean_processing_realtime_factor": 0.7,
            },
            "full_frame_reference": {"fall_event_recall": 0.6},
        }
    )
    missing = evaluate_engineering_gate({"gated": {}})

    assert passing["passed"] is True
    assert passing["scope"] == "public_dataset_engineering_demo_only"
    assert missing["passed"] is False
    assert all(value is False for value in missing["checks"].values())
