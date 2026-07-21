from __future__ import annotations

import mimetypes
import wave
from pathlib import Path
from statistics import mean
from typing import Any

from .contracts import (
    EvidenceLevel,
    MediaProbeReport,
    Modality,
    Observation,
    PrivacyLevel,
    QualityIssue,
    QualityStatus,
    Severity,
    SourceAsset,
    SourceType,
    ensure_source_evidence_compatible,
)
from .privacy import safe_local_uri, sha256_file


PROBE_VERSION = "media-probe-v0.1.0"
AUDIO_SUFFIXES = {".wav", ".wave"}
VIDEO_SUFFIXES = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ts",
    ".webm",
}


def infer_modality(path: Path) -> Modality:
    suffix = path.suffix.lower()
    if suffix in AUDIO_SUFFIXES:
        return Modality.AUDIO
    if suffix in VIDEO_SUFFIXES:
        return Modality.VIDEO
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("audio/"):
        return Modality.AUDIO
    if guessed and guessed.startswith("video/"):
        return Modality.VIDEO
    return Modality.UNKNOWN


def _probe_wav(path: Path) -> tuple[dict[str, Any], list[QualityIssue]]:
    issues: list[QualityIssue] = []
    try:
        with wave.open(str(path), "rb") as stream:
            channels = stream.getnchannels()
            sample_width_bytes = stream.getsampwidth()
            sample_rate_hz = stream.getframerate()
            frame_count = stream.getnframes()
            duration_s = frame_count / sample_rate_hz if sample_rate_hz else None
            metadata = {
                "container": "wav",
                "channels": channels,
                "sample_width_bits": sample_width_bytes * 8,
                "sample_rate_hz": sample_rate_hz,
                "frame_count": frame_count,
                "duration_s": round(duration_s, 6) if duration_s is not None else None,
                "compression_type": stream.getcomptype(),
            }
    except (wave.Error, EOFError) as error:
        metadata = {"container": "wav", "decode_status": "failed"}
        issues.append(
            QualityIssue(
                code="wav_decode_failed",
                severity=Severity.ERROR,
                message="WAV metadata could not be decoded",
                details={"error_type": type(error).__name__},
            )
        )
    return metadata, issues


def _fourcc(value: float) -> str | None:
    integer = int(value)
    if integer <= 0:
        return None
    text = "".join(chr((integer >> (8 * index)) & 0xFF) for index in range(4))
    return text.replace("\x00", "").strip() or None


def _probe_video(
    path: Path,
    sample_count: int = 5,
) -> tuple[dict[str, Any], list[QualityIssue]]:
    issues: list[QualityIssue] = []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return (
            {"opencv_available": False, "decode_status": "not_attempted"},
            [
                QualityIssue(
                    code="opencv_unavailable",
                    severity=Severity.WARNING,
                    message="Install the media extra to inspect video metadata",
                )
            ],
        )

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return (
            {"opencv_available": True, "decode_status": "failed"},
            [
                QualityIssue(
                    code="video_open_failed",
                    severity=Severity.ERROR,
                    message="OpenCV could not open the video",
                )
            ],
        )

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s = frame_count / fps if fps > 0 and frame_count >= 0 else None
    metadata: dict[str, Any] = {
        "opencv_available": True,
        "opencv_version": cv2.__version__,
        "decode_status": "opened",
        "width": width,
        "height": height,
        "fps": round(fps, 6) if fps > 0 else None,
        "frame_count": frame_count if frame_count >= 0 else None,
        "duration_s": round(duration_s, 6) if duration_s is not None else None,
        "fourcc": _fourcc(capture.get(cv2.CAP_PROP_FOURCC)),
        "audio_track_status": "not_inspected_by_opencv",
    }

    brightness_values: list[float] = []
    dark_ratios: list[float] = []
    blur_variances: list[float] = []
    decoded_samples = 0
    if frame_count > 0:
        positions = np.linspace(0, max(frame_count - 1, 0), sample_count, dtype=int)
    else:
        positions = np.array([0], dtype=int)

    for position in sorted(set(int(item) for item in positions)):
        capture.set(cv2.CAP_PROP_POS_FRAMES, position)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        decoded_samples += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness_values.append(float(gray.mean()))
        dark_ratios.append(float((gray < 30).mean()))
        blur_variances.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
    capture.release()

    metadata["sampled_frame_count"] = decoded_samples
    if decoded_samples:
        metadata["sample_quality"] = {
            "brightness_mean": round(mean(brightness_values), 4),
            "brightness_min": round(min(brightness_values), 4),
            "dark_pixel_ratio_mean": round(mean(dark_ratios), 6),
            "laplacian_variance_mean": round(mean(blur_variances), 4),
            "laplacian_variance_min": round(min(blur_variances), 4),
        }
    else:
        issues.append(
            QualityIssue(
                code="video_sample_decode_failed",
                severity=Severity.ERROR,
                message="Video opened but no sampled frame could be decoded",
            )
        )

    issues.append(
        QualityIssue(
            code="audio_track_uninspected",
            severity=Severity.INFO,
            message="OpenCV metadata does not prove whether an audio track exists",
        )
    )
    return metadata, issues


def probe_media(
    path: Path,
    evidence_level: EvidenceLevel = EvidenceLevel.E1,
    device_ref: str | None = None,
    elder_ref: str | None = None,
    source_type: SourceType = SourceType.LOCAL_FILE,
) -> MediaProbeReport:
    ensure_source_evidence_compatible(source_type, evidence_level)
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    digest = sha256_file(path)
    modality = infer_modality(path)
    mime_type, _ = mimetypes.guess_type(path.name)
    asset = SourceAsset(
        asset_id=f"asset_{digest[:20]}",
        modality=modality,
        source_type=source_type,
        evidence_level=evidence_level,
        uri=safe_local_uri(path, digest),
        sha256=digest,
        byte_size=path.stat().st_size,
        privacy_level=PrivacyLevel.RAW_SENSITIVE,
        metadata={
            "filename_suffix": path.suffix.lower(),
            "mime_type": mime_type or "application/octet-stream",
            "file_mtime_is_capture_time": False,
        },
    )

    if modality is Modality.AUDIO and path.suffix.lower() in AUDIO_SUFFIXES:
        technical, issues = _probe_wav(path)
    elif modality is Modality.VIDEO:
        technical, issues = _probe_video(path)
    else:
        technical = {"decode_status": "not_attempted"}
        issues = [
            QualityIssue(
                code="unsupported_media_type",
                severity=Severity.WARNING,
                message="Only WAV and common video containers have a specialized probe",
            )
        ]

    error_count = sum(issue.severity is Severity.ERROR for issue in issues)
    warning_count = sum(issue.severity is Severity.WARNING for issue in issues)
    if error_count:
        quality_status = QualityStatus.FAIL
    elif warning_count or modality is Modality.VIDEO:
        quality_status = QualityStatus.PARTIAL
    elif modality is Modality.UNKNOWN:
        quality_status = QualityStatus.UNKNOWN
    else:
        quality_status = QualityStatus.PASS

    observation = Observation(
        observation_id=f"observation_{digest[:20]}_{PROBE_VERSION.rsplit('-', 1)[-1]}",
        asset_id=asset.asset_id,
        elder_ref=elder_ref,
        device_ref=device_ref,
        modality=modality,
        quality_status=quality_status,
        quality_metrics={
            "probe_error_count": error_count,
            "probe_warning_count": warning_count,
            "byte_size": asset.byte_size,
        },
        missing_reasons=[
            issue.code
            for issue in issues
            if issue.severity in {Severity.WARNING, Severity.ERROR}
        ],
    )
    return MediaProbeReport(
        probe_version=PROBE_VERSION,
        asset=asset,
        observation=observation,
        technical_metadata=technical,
        issues=issues,
    )
