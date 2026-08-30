"""Subject-isolated CAUCAFall benchmark for the fall-candidate pipeline.

This module is deliberately outside the product CLI. Dataset labels are used only
after label-blind candidate generation to calculate engineering metrics.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any, BinaryIO, Callable, Iterable, Literal
from urllib.request import Request, urlopen

from kangshield.information.contracts import FeatureEvent
from kangshield.information.edge_monitor import (
    BufferedVideoFrame,
    EdgeSelectionPolicy,
    InMemoryEdgeSegment,
    LightweightSegmentSelector,
    SegmentSelection,
    _buffer_video_frame,
)
from kangshield.information.fall_candidates import (
    generate_fall_candidate_episodes,
    load_fall_candidate_policy,
)
from kangshield.information.fall_features import (
    FallMotionFeatureExtractor,
    load_fall_feature_config,
)
from kangshield.information.pose_backend import UltralyticsPoseBackend
from kangshield.information.privacy import sha256_file
from kangshield.information.segment_analysis import pose_feature
from kangshield.information.speech_backend import AudioBuffer


CAUCAFALL_DATASET_ID = "7w7fccy7ky"
CAUCAFALL_VERSION = 5
CAUCAFALL_DOI = "10.17632/7w7fccy7ky.5"
CAUCAFALL_LICENSE = "CC-BY-4.0"
CAUCAFALL_PAGE = "https://data.mendeley.com/datasets/7w7fccy7ky/5"
CAUCAFALL_API = (
    f"https://data.mendeley.com/public-api/datasets/{CAUCAFALL_DATASET_ID}"
)
CAUCAFALL_DEV_SUBJECTS = (1, 2, 3, 4, 5)
CAUCAFALL_HOLDOUT_SUBJECTS = (6, 7, 8, 9, 10)
CAUCAFALL_ACTIVITIES = (
    "Fall backwards",
    "Fall forward",
    "Fall left",
    "Fall right",
    "Fall sitting",
    "Hop",
    "Kneel",
    "Pick up object",
    "Sit down",
    "Walk",
)
ENGINEERING_GATE_REVISION = "caucafall-engineering-demo-gate-v1"
ENGINEERING_GATE_THRESHOLDS = {
    "minimum_gated_fall_event_recall": 0.5,
    "maximum_gated_adl_clip_false_positive_rate": 0.1,
    "minimum_fall_motion_gate_retention": 0.9,
    "maximum_mean_selected_frame_ratio": 0.5,
    "maximum_mean_processing_realtime_factor": 1.0,
    "maximum_recall_loss_vs_full_frame": 0.12,
}
_SUBJECT_RE = re.compile(r"^Subject\.(\d+)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_API_ACCEPT = "application/vnd.mendeley-public-dataset.1+json"


class PublicValidationError(RuntimeError):
    """A deterministic validation or dataset-integrity failure."""


@dataclass(frozen=True)
class CaucafallCase:
    subject: int
    activity: str
    label: Literal["fall", "adl"]
    folder_id: str
    file_id: str
    filename: str
    size_bytes: int
    sha256: str
    download_url: str

    @property
    def case_ref(self) -> str:
        activity = re.sub(r"[^a-z0-9]+", "-", self.activity.lower()).strip("-")
        return f"caucafall-v5-s{self.subject:02d}-{activity}"

    def public_manifest(self) -> dict[str, Any]:
        """Return provenance without a cache path or expiring download URL."""

        return {
            "case_ref": self.case_ref,
            "subject": self.subject,
            "activity": self.activity,
            "label": self.label,
            "source_file": {
                "file_id": self.file_id,
                "filename": self.filename,
                "size_bytes": self.size_bytes,
                "sha256": self.sha256,
            },
        }


def default_cache_root() -> Path:
    """Choose a shared cache filesystem and never silently fall back to /home."""

    configured = os.environ.get("KANGSHIELD_DATA_CACHE")
    if configured:
        return Path(configured).expanduser()
    personal = Path("/cache/DeepLearning") / getpass.getuser()
    if personal.is_dir():
        return personal / "kangshield-public-data"
    return Path("/cache/kangshield-public-data")


def _fetch_json(url: str, *, timeout_seconds: float = 45.0) -> Any:
    request = Request(url, headers={"Accept": _API_ACCEPT, "User-Agent": "kangshield-validation/1"})
    context = ssl.create_default_context()
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        return json.load(response)


def parse_folder_tree(payload: Any) -> list[tuple[int, str, str]]:
    """Map the official flat folder tree to (subject, activity, folder id)."""

    if not isinstance(payload, list):
        raise PublicValidationError("CAUCAFall folder response is not a list")
    subjects: dict[str, int] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        matched = _SUBJECT_RE.fullmatch(str(item.get("name", "")))
        if matched and item.get("id"):
            subject = int(matched.group(1))
            if subject not in range(1, 11):
                raise PublicValidationError("CAUCAFall subject is outside 1..10")
            subjects[str(item["id"])] = subject
    activities: list[tuple[int, str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        parent = str(item.get("parent_id", ""))
        name = str(item.get("name", ""))
        folder_id = str(item.get("id", ""))
        if parent not in subjects or name not in CAUCAFALL_ACTIVITIES or not folder_id:
            continue
        activities.append((subjects[parent], name, folder_id))
    activities.sort(key=lambda item: (item[0], CAUCAFALL_ACTIVITIES.index(item[1])))
    expected = 10 * len(CAUCAFALL_ACTIVITIES)
    if len(activities) != expected:
        raise PublicValidationError(
            f"CAUCAFall folder tree has {len(activities)} activities; expected {expected}"
        )
    return activities


def parse_activity_files(
    payload: Any, *, subject: int, activity: str, folder_id: str
) -> CaucafallCase:
    """Select the single official AVI and reject ambiguous metadata."""

    if not isinstance(payload, list):
        raise PublicValidationError("CAUCAFall file response is not a list")
    videos = []
    for item in payload:
        if not isinstance(item, dict) or not str(item.get("filename", "")).lower().endswith(".avi"):
            continue
        details = item.get("content_details")
        if not isinstance(details, dict):
            continue
        videos.append((item, details))
    if len(videos) != 1:
        raise PublicValidationError(
            f"CAUCAFall subject {subject} activity {activity!r} has {len(videos)} AVI files"
        )
    item, details = videos[0]
    filename = Path(str(item.get("filename", ""))).name
    digest = str(details.get("sha256_hash", "")).lower()
    size = details.get("size", item.get("size"))
    url = str(details.get("download_url", ""))
    if not filename or not _SHA256_RE.fullmatch(digest):
        raise PublicValidationError("CAUCAFall AVI metadata lacks a valid filename or SHA-256")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise PublicValidationError("CAUCAFall AVI metadata has an invalid size")
    if not url.startswith("https://data.mendeley.com/public-files/"):
        raise PublicValidationError("CAUCAFall AVI download URL is outside Mendeley Data")
    label: Literal["fall", "adl"] = "fall" if activity.startswith("Fall ") else "adl"
    return CaucafallCase(
        subject=subject,
        activity=activity,
        label=label,
        folder_id=folder_id,
        file_id=str(item.get("id", "")),
        filename=filename,
        size_bytes=size,
        sha256=digest,
        download_url=url,
    )


def discover_catalog(*, workers: int = 8) -> list[CaucafallCase]:
    if workers <= 0:
        raise ValueError("workers must be positive")
    folders = parse_folder_tree(_fetch_json(f"{CAUCAFALL_API}/folders/{CAUCAFALL_VERSION}"))

    def fetch(item: tuple[int, str, str]) -> CaucafallCase:
        subject, activity, folder_id = item
        url = (
            f"{CAUCAFALL_API}/files?folder_id={folder_id}"
            f"&version={CAUCAFALL_VERSION}"
        )
        return parse_activity_files(
            _fetch_json(url), subject=subject, activity=activity, folder_id=folder_id
        )

    cases: list[CaucafallCase] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(folders))) as pool:
        futures = [pool.submit(fetch, item) for item in folders]
        for future in as_completed(futures):
            cases.append(future.result())
    cases.sort(key=lambda item: (item.subject, CAUCAFALL_ACTIVITIES.index(item.activity)))
    return cases


def _catalog_path(cache_root: Path) -> Path:
    return cache_root / "caucafall" / "v5" / "official-catalog.json"


def load_catalog(cache_root: Path, *, refresh: bool = False, workers: int = 8) -> list[CaucafallCase]:
    path = _catalog_path(cache_root)
    if path.is_file() and not refresh:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("dataset_id") != CAUCAFALL_DATASET_ID or payload.get("version") != 5:
            raise PublicValidationError("cached CAUCAFall catalog has unexpected identity")
        cases = [CaucafallCase(**item) for item in payload.get("cases", [])]
        if len(cases) != 100:
            raise PublicValidationError("cached CAUCAFall catalog is incomplete")
        return cases
    cases = discover_catalog(workers=workers)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    payload = {
        "dataset_id": CAUCAFALL_DATASET_ID,
        "version": CAUCAFALL_VERSION,
        "doi": CAUCAFALL_DOI,
        "license": CAUCAFALL_LICENSE,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "cases": [asdict(case) for case in cases],
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return cases


def cases_for_split(
    cases: Iterable[CaucafallCase], split: Literal["dev", "holdout", "all"]
) -> list[CaucafallCase]:
    if split == "dev":
        subjects = set(CAUCAFALL_DEV_SUBJECTS)
    elif split == "holdout":
        subjects = set(CAUCAFALL_HOLDOUT_SUBJECTS)
    elif split == "all":
        subjects = set(CAUCAFALL_DEV_SUBJECTS + CAUCAFALL_HOLDOUT_SUBJECTS)
    else:
        raise ValueError("split must be dev, holdout, or all")
    selected = [case for case in cases if case.subject in subjects]
    selected.sort(key=lambda item: (item.subject, CAUCAFALL_ACTIVITIES.index(item.activity)))
    return selected


def _case_cache_path(case: CaucafallCase, cache_root: Path) -> Path:
    return (
        cache_root
        / "caucafall"
        / "v5"
        / f"subject-{case.subject:02d}"
        / case.case_ref
        / case.filename
    )


def _verified(path: Path, case: CaucafallCase) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == case.size_bytes
        and sha256_file(path) == case.sha256
    )


def download_case(
    case: CaucafallCase,
    cache_root: Path,
    *,
    opener: Callable[..., BinaryIO] = urlopen,
    timeout_seconds: float = 120.0,
) -> Path:
    """Download one AVI atomically and verify official size and SHA-256."""

    path = _case_cache_path(case, cache_root)
    if _verified(path, case):
        return path
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".part-{os.getpid()}")
    request = Request(case.download_url, headers={"User-Agent": "kangshield-validation/1"})
    digest = hashlib.sha256()
    size = 0
    try:
        with opener(request, timeout=timeout_seconds) as response, temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != case.size_bytes or digest.hexdigest() != case.sha256:
            raise PublicValidationError(
                f"download integrity mismatch for {case.case_ref}"
            )
        os.replace(temporary, path)
        return path
    finally:
        if temporary.exists():
            temporary.unlink()


def decode_video_segment(
    path: Path,
    case: CaucafallCase,
    policy: EdgeSelectionPolicy,
) -> InMemoryEdgeSegment:
    """Decode an official video into the same bounded JPEG memory representation."""

    try:
        import av
        import numpy as np
    except ImportError as error:
        raise PublicValidationError("PyAV and NumPy are required for video validation") from error
    frames: list[BufferedVideoFrame] = []
    first_time: float | None = None
    next_video_ms = 0.0
    width = height = 0
    frame_step_ms = round(1000 / policy.video_sample_fps)
    with av.open(str(path), mode="r") as container:
        videos = list(container.streams.video)
        if len(videos) != 1:
            raise PublicValidationError(f"{case.case_ref} does not contain one video track")
        stream = videos[0]
        fallback_index = 0
        for decoded in container.decode(stream):
            absolute = float(decoded.time) if decoded.time is not None else None
            if absolute is None:
                absolute = fallback_index / max(float(stream.average_rate or 25), 1.0)
            fallback_index += 1
            if first_time is None:
                first_time = absolute
            timestamp_ms = max(0, round((absolute - first_time) * 1000))
            if timestamp_ms + 0.5 < next_video_ms:
                continue
            item, width, height = _buffer_video_frame(decoded, timestamp_ms, policy)
            frames.append(item)
            while next_video_ms <= timestamp_ms + 0.5:
                next_video_ms += 1000 / policy.video_sample_fps
    if not frames or width <= 0 or height <= 0:
        raise PublicValidationError(f"{case.case_ref} has no decodable frames")
    duration_ms = max(frame_step_ms, frames[-1].timestamp_ms + frame_step_ms)
    started = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(days=case.subject)
    return InMemoryEdgeSegment(
        segment_id=case.case_ref,
        device_ref="public-validation-camera",
        started_at=started,
        ended_at=started + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        frames=tuple(frames),
        audio=AudioBuffer(
            samples=np.zeros(0, dtype=np.float32),
            sample_rate_hz=policy.audio_sample_rate_hz,
            duration_ms=duration_ms,
        ),
        frame_width=width,
        frame_height=height,
        cloud_recording_ref=f"public-dataset:{case.file_id}",
    )


def _full_selection(segment: InMemoryEdgeSegment, policy: EdgeSelectionPolicy) -> SegmentSelection:
    return SegmentSelection(
        video_frames=segment.frames,
        audio_windows_ms=(),
        key_windows=(),
        motion_threshold=0.0,
        audio_threshold=policy.audio_min_rms,
    )


def _analyze_selection(
    *,
    case: CaucafallCase,
    segment: InMemoryEdgeSegment,
    selection: SegmentSelection,
    pose: UltralyticsPoseBackend,
    sample_fps: float,
    feature_policy_path: Path,
    candidate_policy_path: Path,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    feature_config = load_fall_feature_config(feature_policy_path)
    candidate_policy = load_fall_candidate_policy(candidate_policy_path)
    if feature_config.feature_version != candidate_policy.input_fall_feature_version:
        raise PublicValidationError("fall feature and candidate policy versions differ")
    reset = getattr(pose, "reset", None)
    if callable(reset):
        reset()
    extractor = FallMotionFeatureExtractor(
        feature_config,
        frame_width=segment.frame_width,
        frame_height=segment.frame_height,
    )
    values = []
    people_frames = 0
    for sequence, item in enumerate(selection.video_frames):
        frame = cv2.imdecode(np.frombuffer(item.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise PublicValidationError(f"selected frame decode failed for {case.case_ref}")
        detections = pose.infer(frame)
        people_frames += int(bool(detections))
        event = pose_feature(
            run_id=case.case_ref,
            sequence=sequence,
            timestamp_ms=item.timestamp_ms,
            sample_fps=sample_fps,
            observation_id=case.case_ref,
            detections=detections,
            model_digest=pose.bindings[0].model_digest,
            extractor_version=pose.bindings[0].model_version,
        )
        values.append(extractor.process(FeatureEvent.model_validate(event)))
    episodes = generate_fall_candidate_episodes(
        values,
        duration_ms=segment.duration_ms,
        case_ref=case.case_ref,
        policy=candidate_policy,
    )
    available = [item for item in values if item.active_path != "unavailable"]
    bbox_ratios = [
        item.bbox_width_height_ratio
        for item in available
        if item.bbox_width_height_ratio is not None
    ]
    center_drops = [
        item.center_drop_frame_height_ratio
        for item in available
        if item.center_drop_frame_height_ratio is not None
    ]
    centers_y = [
        item.bbox_center_y_ratio
        for item in available
        if item.bbox_center_y_ratio is not None
    ]
    bottoms_y = [
        item.bbox_bottom_y_ratio
        for item in available
        if item.bbox_bottom_y_ratio is not None
    ]
    areas = [
        item.bbox_area_frame_ratio
        for item in available
        if item.bbox_area_frame_ratio is not None
    ]
    baseline_center_y = median(centers_y[: min(5, len(centers_y))]) if centers_y else None
    timestamp_gaps = [
        current.timestamp_ms - previous.timestamp_ms
        for previous, current in zip(values, values[1:])
    ]
    frame_interval_ms = round(median(timestamp_gaps)) if timestamp_gaps else 200
    longest_absence_ms = 0
    absence_started_ms: int | None = None
    for item in values:
        if item.active_path == "unavailable":
            if absence_started_ms is None:
                absence_started_ms = item.timestamp_ms
            longest_absence_ms = max(
                longest_absence_ms,
                item.timestamp_ms + frame_interval_ms - absence_started_ms,
            )
        else:
            absence_started_ms = None
    terminal_absence_ms = (
        max(0, segment.duration_ms - available[-1].timestamp_ms - frame_interval_ms)
        if available
        else segment.duration_ms
    )
    history_reset_reasons = sorted(
        {
            reason
            for item in available
            for reason in item.fallback_reasons
            if "history_reset" in reason
        }
    )
    diagnostics = {
        "available_pose_frame_count": len(available),
        "tracked_pose_frame_count": sum(
            item.selected_track_id is not None for item in available
        ),
        "history_reset_frame_count": sum(
            any("history_reset" in reason for reason in item.fallback_reasons)
            for item in available
        ),
        "history_reset_reason_counts": {
            reason: sum(
                reason in item.fallback_reasons for item in available
            )
            for reason in history_reset_reasons
        },
        "bbox_horizontal_frame_count": sum(
            item.bbox_horizontal_proxy is True for item in available
        ),
        "torso_horizontal_frame_count": sum(
            item.keypoint_gate.torso_horizontal_proxy is True for item in available
        ),
        "posture_horizontal_frame_count": sum(
            item.posture_horizontal_proxy is True for item in available
        ),
        "rapid_descent_frame_count": sum(
            item.rapid_descent_proxy is True for item in available
        ),
        "low_motion_frame_count": sum(
            item.low_motion_proxy is True for item in available
        ),
        "maximum_bbox_width_height_ratio": round(max(bbox_ratios), 6)
        if bbox_ratios
        else None,
        "maximum_center_drop_frame_height_ratio": round(max(center_drops), 6)
        if center_drops
        else None,
        "maximum_center_y_ratio": round(max(centers_y), 6) if centers_y else None,
        "maximum_bottom_y_ratio": round(max(bottoms_y), 6) if bottoms_y else None,
        "maximum_bbox_area_frame_ratio": round(max(areas), 6) if areas else None,
        "center_y_drop_from_initial_baseline": round(
            max(centers_y) - baseline_center_y, 6
        )
        if centers_y and baseline_center_y is not None
        else None,
        "last_center_y_ratio": round(centers_y[-1], 6) if centers_y else None,
        "last_bottom_y_ratio": round(bottoms_y[-1], 6) if bottoms_y else None,
        "last_bbox_width_height_ratio": round(bbox_ratios[-1], 6)
        if bbox_ratios
        else None,
        "longest_person_absence_ms": longest_absence_ms,
        "terminal_person_absence_ms": terminal_absence_ms,
        "maximum_posture_horizontal_duration_ms": max(
            (
                item.posture_horizontal_duration_ms or 0
                for item in available
            ),
            default=0,
        ),
        "maximum_bbox_horizontal_duration_ms": max(
            (item.horizontal_duration_ms or 0 for item in available),
            default=0,
        ),
        "maximum_near_floor_duration_ms": max(
            (item.near_floor_duration_ms or 0 for item in available),
            default=0,
        ),
    }
    return {
        "selected_frame_count": len(selection.video_frames),
        "pose_frames_with_people": people_frames,
        "pose_person_coverage": round(people_frames / len(selection.video_frames), 6)
        if selection.video_frames
        else 0.0,
        "candidate_count": len(episodes),
        "candidate_detected_at_ms": [item.detected_at_ms for item in episodes],
        "candidate_trigger_paths": [item.trigger_path for item in episodes],
        "engineering_diagnostics": diagnostics,
    }


def benchmark_case(
    case: CaucafallCase,
    path: Path,
    *,
    edge_policy: EdgeSelectionPolicy,
    pose: UltralyticsPoseBackend,
    feature_policy_path: Path,
    candidate_policy_path: Path,
    mode: Literal["gated", "full", "both"] = "both",
) -> dict[str, Any]:
    segment = decode_video_segment(path, case, edge_policy)
    result = case.public_manifest()
    result["media"] = {
        "duration_ms": segment.duration_ms,
        "screened_frame_count": len(segment.frames),
        "contains_audio": False,
    }
    if mode in {"gated", "both"}:
        selection = LightweightSegmentSelector(edge_policy).select(segment)
        started = perf_counter()
        gated = _analyze_selection(
            case=case,
            segment=segment,
            selection=selection,
            pose=pose,
            sample_fps=edge_policy.video_sample_fps,
            feature_policy_path=feature_policy_path,
            candidate_policy_path=candidate_policy_path,
        )
        processing_seconds = perf_counter() - started
        gated.update(
            {
                "selection_ratio": round(len(selection.video_frames) / len(segment.frames), 6),
                "motion_threshold": selection.motion_threshold,
                "motion_retained": any(
                    "motion" in window.reasons for window in selection.key_windows
                ),
                "processing_seconds": round(processing_seconds, 6),
                "processing_realtime_factor": round(
                    processing_seconds / (segment.duration_ms / 1000), 6
                ),
            }
        )
        result["gated"] = gated
    if mode in {"full", "both"}:
        started = perf_counter()
        full = _analyze_selection(
            case=case,
            segment=segment,
            selection=_full_selection(segment, edge_policy),
            pose=pose,
            sample_fps=edge_policy.video_sample_fps,
            feature_policy_path=feature_policy_path,
            candidate_policy_path=candidate_policy_path,
        )
        processing_seconds = perf_counter() - started
        full.update(
            {
                "processing_seconds": round(processing_seconds, 6),
                "processing_realtime_factor": round(
                    processing_seconds / (segment.duration_ms / 1000), 6
                ),
            }
        )
        result["full_frame_reference"] = full
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def aggregate_metrics(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    falls = [item for item in rows if item["label"] == "fall"]
    adls = [item for item in rows if item["label"] == "adl"]
    metrics: dict[str, Any] = {
        "clip_count": len(rows),
        "fall_clip_count": len(falls),
        "adl_clip_count": len(adls),
    }
    for key, output_name in (("gated", "gated"), ("full_frame_reference", "full_frame_reference")):
        present = [item for item in rows if key in item]
        if not present:
            continue
        present_falls = [item for item in present if item["label"] == "fall"]
        present_adls = [item for item in present if item["label"] == "adl"]
        detected_falls = sum(item[key]["candidate_count"] > 0 for item in present_falls)
        false_adls = sum(item[key]["candidate_count"] > 0 for item in present_adls)
        detection_times = [
            timestamp
            for item in present_falls
            for timestamp in item[key]["candidate_detected_at_ms"][:1]
        ]
        summary: dict[str, Any] = {
            "fall_event_recall": _ratio(detected_falls, len(present_falls)),
            "fall_clips_detected": detected_falls,
            "adl_clip_false_positive_rate": _ratio(false_adls, len(present_adls)),
            "adl_clips_flagged": false_adls,
            "median_first_detection_ms_from_clip_start": round(median(detection_times))
            if detection_times
            else None,
            "mean_pose_person_coverage": round(
                mean(item[key]["pose_person_coverage"] for item in present), 6
            ),
        }
        realtime_factors = [
            item[key]["processing_realtime_factor"]
            for item in present
            if "processing_realtime_factor" in item[key]
        ]
        if realtime_factors:
            summary["mean_processing_realtime_factor"] = round(
                mean(realtime_factors), 6
            )
        if key == "gated":
            summary["fall_motion_gate_retention"] = _ratio(
                sum(item[key]["motion_retained"] for item in present_falls),
                len(present_falls),
            )
            summary["mean_selected_frame_ratio"] = round(
                mean(item[key]["selection_ratio"] for item in present), 6
            )
        metrics[output_name] = summary
    return metrics


def evaluate_engineering_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a predeclared demo gate without implying clinical validation."""

    gated = metrics.get("gated", {})
    full = metrics.get("full_frame_reference", {})
    recall = gated.get("fall_event_recall")
    full_recall = full.get("fall_event_recall")
    false_positive_rate = gated.get("adl_clip_false_positive_rate")
    motion_retention = gated.get("fall_motion_gate_retention")
    selection_ratio = gated.get("mean_selected_frame_ratio")
    realtime_factor = gated.get("mean_processing_realtime_factor")
    recall_loss = (
        round(max(0.0, full_recall - recall), 6)
        if isinstance(recall, (int, float))
        and isinstance(full_recall, (int, float))
        else None
    )
    observed = {
        "gated_fall_event_recall": recall,
        "gated_adl_clip_false_positive_rate": false_positive_rate,
        "fall_motion_gate_retention": motion_retention,
        "mean_selected_frame_ratio": selection_ratio,
        "mean_processing_realtime_factor": realtime_factor,
        "recall_loss_vs_full_frame": recall_loss,
    }
    thresholds = ENGINEERING_GATE_THRESHOLDS
    checks = {
        "gated_fall_event_recall": isinstance(recall, (int, float))
        and recall >= thresholds["minimum_gated_fall_event_recall"],
        "gated_adl_clip_false_positive_rate": isinstance(
            false_positive_rate, (int, float)
        )
        and false_positive_rate
        <= thresholds["maximum_gated_adl_clip_false_positive_rate"],
        "fall_motion_gate_retention": isinstance(motion_retention, (int, float))
        and motion_retention >= thresholds["minimum_fall_motion_gate_retention"],
        "mean_selected_frame_ratio": isinstance(selection_ratio, (int, float))
        and selection_ratio <= thresholds["maximum_mean_selected_frame_ratio"],
        "mean_processing_realtime_factor": isinstance(realtime_factor, (int, float))
        and realtime_factor
        <= thresholds["maximum_mean_processing_realtime_factor"],
        "recall_loss_vs_full_frame": isinstance(recall_loss, (int, float))
        and recall_loss <= thresholds["maximum_recall_loss_vs_full_frame"],
    }
    return {
        "revision": ENGINEERING_GATE_REVISION,
        "scope": "public_dataset_engineering_demo_only",
        "thresholds": thresholds,
        "observed": observed,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _policy_binding(path: Path) -> dict[str, str]:
    return {"filename": path.name, "sha256": sha256_file(path)}


def build_report(
    *,
    split: str,
    subjects: Iterable[int],
    results: list[dict[str, Any]],
    edge_policy_path: Path,
    feature_policy_path: Path,
    candidate_policy_path: Path,
    pose: UltralyticsPoseBackend,
) -> dict[str, Any]:
    metrics = aggregate_metrics(results)
    return {
        "schema_version": "1.0",
        "status": "pilot_unvalidated",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "CAUCAFall",
            "dataset_id": CAUCAFALL_DATASET_ID,
            "version": CAUCAFALL_VERSION,
            "doi": CAUCAFALL_DOI,
            "source_url": CAUCAFALL_PAGE,
            "license": CAUCAFALL_LICENSE,
        },
        "evaluation_contract": {
            "split": split,
            "subjects": sorted(set(subjects)),
            "development_subjects": list(CAUCAFALL_DEV_SUBJECTS),
            "holdout_subjects": list(CAUCAFALL_HOLDOUT_SUBJECTS),
            "labels_visible_to_candidate_generation": False,
            "unit": "one activity clip",
            "audio_fraud_or_mental_wellbeing_evaluated": False,
        },
        "bindings": {
            "edge_selection_policy": _policy_binding(edge_policy_path),
            "fall_feature_policy": _policy_binding(feature_policy_path),
            "fall_candidate_policy": _policy_binding(candidate_policy_path),
            "pose_model": pose.bindings[0].model_dump(mode="json"),
        },
        "metrics": metrics,
        "engineering_gate": evaluate_engineering_gate(metrics),
        "execution": {
            "surface": "slurm_compute_node"
            if os.environ.get("SLURM_JOB_ID")
            else "direct_process",
            "login_node_compute_prohibited": True,
        },
        "cases": results,
        "limitations": [
            "public_dataset_contains_simulated_falls_not_real_incidents",
            "single_dataset_results_do_not_establish_target_camera_performance",
            "clip_level_labels_do_not_supply_exact_fall_onset_latency",
            "video_only_benchmark_does_not_evaluate_audio_or_cross_modal_rules",
            "engineering_validation_is_not_clinical_validation_or_a_probability",
        ],
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a subject-isolated CAUCAFall fall-candidate benchmark."
    )
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument("--mode", choices=("gated", "full", "both"), default="both")
    parser.add_argument("--cache-root", type=Path, default=default_cache_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--accept-license", required=True)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="download and verify selected media without loading or running a model",
    )
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--catalog-workers", type=int, default=8)
    parser.add_argument("--download-workers", type=int, default=4)
    parser.add_argument("--max-clips", type=int)
    parser.add_argument("--activity", action="append", choices=CAUCAFALL_ACTIVITIES)
    parser.add_argument(
        "--subject",
        action="append",
        type=int,
        choices=range(1, 11),
        help="restrict an already isolated split to specific subject numbers",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(
            os.environ.get("KANGSHIELD_POSE_MODEL", "models/yolo26s-pose.pt")
        ),
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--pose-confidence", type=float)
    parser.add_argument("--pose-image-size", type=int)
    parser.add_argument("--edge-policy", type=Path, default=Path("configs/v2-edge-segment-policy.json"))
    parser.add_argument("--fall-feature-policy", type=Path, default=Path("configs/v1-g4-fall-features.json"))
    parser.add_argument("--fall-candidate-policy", type=Path, default=Path("configs/v1-g4-event-candidate-policy.json"))
    args = parser.parse_args(argv)
    if args.accept_license != CAUCAFALL_LICENSE:
        parser.error(f"--accept-license must be exactly {CAUCAFALL_LICENSE}")
    if args.max_clips is not None and args.max_clips <= 0:
        parser.error("--max-clips must be positive")
    if args.download_workers <= 0:
        parser.error("--download-workers must be positive")
    if args.pose_confidence is not None and not 0 < args.pose_confidence <= 1:
        parser.error("--pose-confidence must be in (0, 1]")
    if args.pose_image_size is not None and args.pose_image_size <= 0:
        parser.error("--pose-image-size must be positive")
    if not args.prepare_only and args.output is None:
        parser.error("--output is required unless --prepare-only is used")

    args.cache_root.mkdir(parents=True, exist_ok=True)
    _progress(f"catalog: CAUCAFall v5 -> {args.split} split")
    catalog = load_catalog(
        args.cache_root,
        refresh=args.refresh_catalog,
        workers=args.catalog_workers,
    )
    cases = cases_for_split(catalog, args.split)
    if args.subject:
        wanted_subjects = set(args.subject)
        cases = [case for case in cases if case.subject in wanted_subjects]
    if args.activity:
        wanted = set(args.activity)
        cases = [case for case in cases if case.activity in wanted]
    if args.max_clips is not None:
        cases = cases[: args.max_clips]
    if not cases:
        raise PublicValidationError("no CAUCAFall cases selected")

    _progress(f"download: verifying {len(cases)} official AVI files in cache")
    paths: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=min(args.download_workers, len(cases))) as pool:
        futures = {
            pool.submit(download_case, case, args.cache_root): case for case in cases
        }
        for index, future in enumerate(as_completed(futures), 1):
            case = futures[future]
            paths[case.case_ref] = future.result()
            _progress(f"download: {index}/{len(cases)} {case.case_ref}")

    if args.prepare_only:
        print(
            json.dumps(
                {
                    "dataset": "CAUCAFall",
                    "version": CAUCAFALL_VERSION,
                    "split": args.split,
                    "verified_clip_count": len(paths),
                    "subjects": sorted({case.subject for case in cases}),
                    "model_loaded": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    if not args.model.is_file():
        parser.error(f"pose model is unavailable: {args.model}")

    edge_policy = EdgeSelectionPolicy.load(args.edge_policy)
    if sha256_file(args.model) != edge_policy.pose_model_sha256:
        parser.error("pose model SHA-256 does not match the edge policy")
    pose = UltralyticsPoseBackend(
        model=args.model,
        device=args.device,
        image_size=args.pose_image_size or edge_policy.pose_model_image_size,
        confidence=(
            args.pose_confidence
            if args.pose_confidence is not None
            else edge_policy.pose_model_confidence
        ),
        track=True,
    )
    pose_binding = pose.bindings[0]
    if (
        pose_binding.model_name != edge_policy.pose_model_name
        or pose_binding.model_digest != edge_policy.pose_model_sha256
        or pose_binding.license != edge_policy.pose_model_license
    ):
        raise PublicValidationError("pose model binding differs from edge policy")
    results = []
    for index, case in enumerate(cases, 1):
        _progress(f"benchmark: {index}/{len(cases)} {case.case_ref}")
        results.append(
            benchmark_case(
                case,
                paths[case.case_ref],
                edge_policy=edge_policy,
                pose=pose,
                feature_policy_path=args.fall_feature_policy,
                candidate_policy_path=args.fall_candidate_policy,
                mode=args.mode,
            )
        )
    report = build_report(
        split=args.split,
        subjects=(case.subject for case in cases),
        results=results,
        edge_policy_path=args.edge_policy,
        feature_policy_path=args.fall_feature_policy,
        candidate_policy_path=args.fall_candidate_policy,
        pose=pose,
    )
    assert args.output is not None
    write_report(report, args.output)
    _progress(f"report: wrote {args.output}")
    print(json.dumps(report["metrics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
