from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import tarfile
import urllib.request
import wave
import zipfile
from pathlib import Path
from statistics import median
from typing import Any

from .artifacts import atomic_write_json


FLEURS_FIELDS = (
    "sentence_id",
    "wav_filename",
    "transcription",
    "raw_transcription",
    "words",
    "num_samples",
    "gender",
)
URFD_LABEL_LEGEND = {
    "-1": "not_lying",
    "0": "falling_transition",
    "1": "lying",
    "null": "unlabeled",
}
FRAME_NUMBER_PATTERN = re.compile(r"-(\d+)\.png$", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset_manifest(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("schema_version") != "1.0":
        raise ValueError("unsupported dataset manifest schema")
    if manifest.get("evidence_level") != "E1":
        raise ValueError("the public fixed suite must remain E1")
    if manifest.get("pairing_kind") != "cross_dataset_synthetic_common_zero":
        raise ValueError("the public fixed suite must declare synthetic pairing")
    if not manifest.get("datasets") or not manifest.get("cases"):
        raise ValueError("dataset manifest must contain datasets and cases")
    return manifest


def verify_file(path: Path, *, byte_size: int, sha256: str) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_size = path.stat().st_size
    if actual_size != byte_size:
        raise ValueError(
            f"size mismatch for {path}: expected {byte_size}, got {actual_size}"
        )
    actual_sha256 = sha256_file(path)
    if actual_sha256 != sha256:
        raise ValueError(
            f"SHA-256 mismatch for {path}: expected {sha256}, got {actual_sha256}"
        )


def download_and_verify(
    url: str,
    path: Path,
    *,
    byte_size: int,
    sha256: str,
) -> None:
    """Download a pinned source, resuming a partial response when supported."""

    path = Path(path)
    if path.is_file():
        verify_file(path, byte_size=byte_size, sha256=sha256)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    partial_size = partial.stat().st_size if partial.is_file() else 0
    if partial_size > byte_size:
        partial.unlink()
        partial_size = 0
    if partial_size == byte_size:
        verify_file(partial, byte_size=byte_size, sha256=sha256)
        partial.replace(path)
        return
    headers = {"User-Agent": "KangShield-V1-dataset-preparer/1.0"}
    if partial_size:
        headers["Range"] = f"bytes={partial_size}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        append = partial_size > 0 and getattr(response, "status", None) == 206
        mode = "ab" if append else "wb"
        with partial.open(mode) as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
    verify_file(partial, byte_size=byte_size, sha256=sha256)
    partial.replace(path)


def _read_urfd_sync(path: Path) -> dict[int, int]:
    timestamps: dict[int, int] = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 2:
                continue
            frame_number = int(row[0])
            timestamp_ms = int(row[1])
            if frame_number in timestamps:
                raise ValueError(f"duplicate URFD sync frame {frame_number}")
            timestamps[frame_number] = timestamp_ms
    if not timestamps:
        raise ValueError(f"empty URFD synchronization file: {path}")
    return timestamps


def _read_urfd_labels(path: Path, sequence: str) -> dict[int, int]:
    labels: dict[int, int] = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 3 or row[0] != sequence:
                continue
            frame_number = int(row[1])
            label = int(row[2])
            if label not in {-1, 0, 1}:
                raise ValueError(f"unexpected URFD posture label: {label}")
            labels[frame_number] = label
    if not labels:
        raise ValueError(f"no URFD labels for {sequence} in {path}")
    return labels


def _zip_png_members(archive: zipfile.ZipFile) -> list[tuple[int, str]]:
    members: list[tuple[int, str]] = []
    for name in archive.namelist():
        match = FRAME_NUMBER_PATTERN.search(name)
        if match:
            members.append((int(match.group(1)), name))
    members.sort()
    if not members:
        raise ValueError("URFD archive contains no numbered PNG frames")
    if len({number for number, _ in members}) != len(members):
        raise ValueError("URFD archive contains duplicate frame numbers")
    return members


def convert_urfd_sequence(
    *,
    archive_path: Path,
    sync_path: Path,
    labels_path: Path,
    sequence: str,
    video_path: Path,
    annotation_path: Path,
) -> dict[str, Any]:
    """Convert one URFD PNG archive to a constant-rate MJPG replay plus sidecar."""

    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise RuntimeError("OpenCV and NumPy are required for URFD conversion") from error

    timestamps = _read_urfd_sync(sync_path)
    labels = _read_urfd_labels(labels_path, sequence)
    ordered_timestamps = [timestamps[number] for number in sorted(timestamps)]
    deltas = [
        current - previous
        for previous, current in zip(ordered_timestamps, ordered_timestamps[1:])
        if current > previous
    ]
    if not deltas:
        raise ValueError(f"cannot infer frame period for {sequence}")
    frame_period_ms = float(median(deltas))
    fps = 1000.0 / frame_period_ms

    video_path = Path(video_path)
    annotation_path = Path(annotation_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_video = video_path.with_name(f".{video_path.stem}.partial.avi")
    temporary_video.unlink(missing_ok=True)
    writer = None
    frame_records: list[dict[str, Any]] = []
    width = 0
    height = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _zip_png_members(archive)
            for output_index, (frame_number, member_name) in enumerate(members):
                if frame_number not in timestamps:
                    raise ValueError(
                        f"URFD frame {frame_number} lacks synchronization metadata"
                    )
                encoded = np.frombuffer(archive.read(member_name), dtype=np.uint8)
                frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                if frame is None:
                    raise ValueError(f"cannot decode URFD frame: {member_name}")
                frame_height, frame_width = frame.shape[:2]
                if writer is None:
                    width, height = frame_width, frame_height
                    writer = cv2.VideoWriter(
                        str(temporary_video),
                        cv2.VideoWriter_fourcc(*"MJPG"),
                        fps,
                        (width, height),
                    )
                    if not writer.isOpened():
                        raise RuntimeError("OpenCV MJPG video writer is unavailable")
                elif (frame_width, frame_height) != (width, height):
                    raise ValueError("URFD sequence changes frame dimensions")
                writer.write(frame)
                replay_timestamp_ms = round(output_index * 1000.0 / fps)
                source_timestamp_ms = timestamps[frame_number]
                frame_records.append(
                    {
                        "output_frame_index": output_index,
                        "source_frame_number": frame_number,
                        "source_timestamp_ms": source_timestamp_ms,
                        "replay_timestamp_ms": replay_timestamp_ms,
                        "alignment_error_ms": replay_timestamp_ms
                        - source_timestamp_ms,
                        "posture_label": labels.get(frame_number),
                    }
                )
    except Exception:
        temporary_video.unlink(missing_ok=True)
        raise
    finally:
        if writer is not None:
            writer.release()
    if not temporary_video.is_file() or temporary_video.stat().st_size == 0:
        raise RuntimeError(f"failed to encode URFD sequence: {sequence}")
    temporary_video.replace(video_path)

    maximum_error = max(
        (abs(item["alignment_error_ms"]) for item in frame_records),
        default=0,
    )
    annotation = {
        "schema_version": "1.0",
        "dataset_id": "urfd",
        "sequence": sequence,
        "video_class": "fall" if sequence.startswith("fall-") else "adl",
        "video_codec": "MJPG",
        "fps": round(fps, 9),
        "frame_period_ms": frame_period_ms,
        "width": width,
        "height": height,
        "frame_count": len(frame_records),
        "labeled_frame_count": sum(
            item["posture_label"] is not None for item in frame_records
        ),
        "maximum_replay_alignment_error_ms": maximum_error,
        "posture_label_legend": URFD_LABEL_LEGEND,
        "frames": frame_records,
    }
    atomic_write_json(annotation_path, annotation)
    return annotation


def read_fleurs_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t", fieldnames=FLEURS_FIELDS)
        for source in reader:
            filename = source["wav_filename"]
            if filename in rows:
                raise ValueError(f"duplicate FLEURS audio filename: {filename}")
            rows[filename] = {
                **source,
                "num_samples": int(source["num_samples"]),
            }
    if not rows:
        raise ValueError(f"empty FLEURS metadata file: {path}")
    return rows


def extract_fleurs_audio(
    *,
    archive_path: Path,
    filenames: set[str],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        members: dict[str, tarfile.TarInfo] = {}
        for member in archive.getmembers():
            basename = Path(member.name).name
            if basename in filenames and member.isfile():
                if basename in members:
                    raise ValueError(f"duplicate FLEURS tar member: {basename}")
                members[basename] = member
        missing = filenames - members.keys()
        if missing:
            raise ValueError(f"FLEURS archive lacks selected audio: {sorted(missing)}")
        for filename in sorted(filenames):
            target = output_dir / filename
            temporary = output_dir / f".{filename}.partial"
            source = archive.extractfile(members[filename])
            if source is None:
                raise ValueError(f"cannot read FLEURS tar member: {filename}")
            try:
                with source, temporary.open("wb") as stream:
                    shutil.copyfileobj(source, stream, length=1024 * 1024)
                temporary.replace(target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            extracted[filename] = target
    return extracted


def _normalize_and_validate_fleurs_wav(
    path: Path,
    *,
    expected_samples: int,
) -> dict[str, Any]:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError(
            "SoundFile and NumPy are required to normalize FLEURS float WAV files"
        ) from error

    samples, sample_rate_hz = sf.read(
        str(path),
        dtype="float32",
        always_2d=True,
    )
    if sample_rate_hz != 16000:
        raise ValueError(f"FLEURS sample is not 16 kHz: {path}")
    if samples.shape[0] != expected_samples:
        raise ValueError(
            f"FLEURS sample-count mismatch for {path.name}: "
            f"expected {expected_samples}, got {samples.shape[0]}"
        )
    mono = np.ascontiguousarray(samples.mean(axis=1), dtype=np.float32)
    temporary = path.with_name(f".{path.name}.pcm16.partial")
    try:
        sf.write(
            str(temporary),
            mono,
            sample_rate_hz,
            subtype="PCM_16",
            format="WAV",
        )
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    with wave.open(str(path), "rb") as stream:
        metadata = {
            "channels": stream.getnchannels(),
            "sample_width_bits": stream.getsampwidth() * 8,
            "sample_rate_hz": stream.getframerate(),
            "num_samples": stream.getnframes(),
            "compression_type": stream.getcomptype(),
        }
    if metadata["sample_rate_hz"] != 16000:
        raise ValueError(f"normalized FLEURS sample is not 16 kHz PCM: {path}")
    if metadata["channels"] != 1 or metadata["sample_width_bits"] != 16:
        raise ValueError(f"normalized FLEURS sample is not mono PCM16: {path}")
    if metadata["compression_type"] != "NONE":
        raise ValueError(f"FLEURS sample is not uncompressed PCM: {path}")
    if metadata["num_samples"] != expected_samples:
        raise ValueError(
            f"FLEURS sample-count mismatch for {path.name}: "
            f"expected {expected_samples}, got {metadata['num_samples']}"
        )
    metadata["duration_ms"] = round(expected_samples * 1000 / 16000)
    return metadata


def prepare_v1_m2b_dataset(
    *,
    manifest_path: Path,
    download_dir: Path,
    output_dir: Path,
    accept_urfd_noncommercial_license: bool,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    download_dir = Path(download_dir)
    output_dir = Path(output_dir)
    manifest = load_dataset_manifest(manifest_path)
    urfd = next(
        dataset for dataset in manifest["datasets"] if dataset["dataset_id"] == "urfd"
    )
    if urfd.get("license_acceptance_required") and not accept_urfd_noncommercial_license:
        raise PermissionError(
            "URFD is CC-BY-NC-SA-4.0; rerun with explicit non-commercial "
            "license acceptance after reviewing configs/v1-m2b-datasets.json"
        )

    source_lock: list[dict[str, Any]] = []
    for dataset in manifest["datasets"]:
        for item in dataset["files"]:
            target = download_dir / item["path"]
            download_and_verify(
                item["url"],
                target,
                byte_size=item["byte_size"],
                sha256=item["sha256"],
            )
            source_lock.append(
                {
                    "dataset_id": dataset["dataset_id"],
                    "path": item["path"],
                    "byte_size": item["byte_size"],
                    "sha256": item["sha256"],
                }
            )

    fleurs_rows = read_fleurs_rows(download_dir / "fleurs/dev.tsv")
    selected_filenames = {case["audio_filename"] for case in manifest["cases"]}
    extracted_audio = extract_fleurs_audio(
        archive_path=download_dir / "fleurs/dev.tar.gz",
        filenames=selected_filenames,
        output_dir=output_dir / "audio",
    )

    benchmark_cases: list[dict[str, Any]] = []
    processed_files: list[dict[str, Any]] = []
    converted_sequences: set[str] = set()
    for case in manifest["cases"]:
        sequence = case["video_sequence"]
        video_path = output_dir / "video" / f"{sequence}.avi"
        annotation_path = output_dir / "annotations" / f"{sequence}.json"
        if sequence not in converted_sequences:
            label_filename = (
                "urfall-cam0-falls.csv"
                if case["video_class"] == "fall"
                else "urfall-cam0-adls.csv"
            )
            convert_urfd_sequence(
                archive_path=download_dir
                / "urfd"
                / f"{sequence}-cam0-rgb.zip",
                sync_path=download_dir / "urfd" / f"{sequence}-data.csv",
                labels_path=download_dir / "urfd" / label_filename,
                sequence=sequence,
                video_path=video_path,
                annotation_path=annotation_path,
            )
            converted_sequences.add(sequence)
            for path, kind in (
                (video_path, "video_replay"),
                (annotation_path, "video_annotation"),
            ):
                processed_files.append(
                    {
                        "kind": kind,
                        "path": path.relative_to(output_dir).as_posix(),
                        "byte_size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )

        filename = case["audio_filename"]
        row = fleurs_rows.get(filename)
        if row is None:
            raise ValueError(f"selected FLEURS row not found: {filename}")
        if row["gender"] != case["expected_gender"]:
            raise ValueError(f"FLEURS gender mismatch for {filename}")
        audio_path = extracted_audio[filename]
        audio_metadata = _normalize_and_validate_fleurs_wav(
            audio_path,
            expected_samples=case["expected_num_samples"],
        )
        processed_files.append(
            {
                "kind": "audio",
                "path": audio_path.relative_to(output_dir).as_posix(),
                "byte_size": audio_path.stat().st_size,
                "sha256": sha256_file(audio_path),
            }
        )
        benchmark_cases.append(
            {
                "schema_version": "1.0",
                "case_id": case["case_id"],
                "evidence_level": "E1",
                "pairing_kind": manifest["pairing_kind"],
                "video_path": video_path.relative_to(output_dir).as_posix(),
                "audio_path": audio_path.relative_to(output_dir).as_posix(),
                "annotation_path": annotation_path.relative_to(output_dir).as_posix(),
                "video_dataset": "urfd",
                "video_sequence": sequence,
                "video_class": case["video_class"],
                "audio_dataset": "fleurs-cmn-hans-cn",
                "audio_sample": filename,
                "audio_gender": row["gender"].lower(),
                "audio_duration_ms": audio_metadata["duration_ms"],
                "reference_transcript": row["transcription"],
                "limitations": [
                    "cross_dataset_audio_video_pairing",
                    "synthetic_common_zero_time",
                    "not_target_device_evidence",
                    "not_natural_multimodal_semantics",
                ],
            }
        )

    benchmark = {
        "schema_version": "1.0",
        "benchmark_id": manifest["benchmark_id"],
        "evidence_level": manifest["evidence_level"],
        "pairing_kind": manifest["pairing_kind"],
        "source_manifest_sha256": sha256_file(manifest_path),
        "dataset_licenses": {
            dataset["dataset_id"]: dataset["license"]
            for dataset in manifest["datasets"]
        },
        "cases": benchmark_cases,
        "limitations": manifest["limitations"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_path = output_dir / "benchmark-cases.json"
    atomic_write_json(benchmark_path, benchmark)
    processed_files.append(
        {
            "kind": "benchmark_cases",
            "path": benchmark_path.relative_to(output_dir).as_posix(),
            "byte_size": benchmark_path.stat().st_size,
            "sha256": sha256_file(benchmark_path),
        }
    )
    lock = {
        "schema_version": "1.0",
        "benchmark_id": manifest["benchmark_id"],
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_files": sorted(source_lock, key=lambda item: item["path"]),
        "processed_files": sorted(processed_files, key=lambda item: item["path"]),
    }
    atomic_write_json(output_dir / "dataset-lock.json", lock)
    return {
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_cases": str(benchmark_path),
        "case_count": len(benchmark_cases),
        "source_file_count": len(source_lock),
        "processed_file_count": len(processed_files),
    }
