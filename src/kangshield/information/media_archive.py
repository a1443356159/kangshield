"""Bounded owner-only MP4 archives derived from in-memory anomaly windows."""

from __future__ import annotations

import hashlib
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from .contracts import CandidateMediaArchive, DomainCandidate
from .longitudinal.store import LongitudinalStore


class MediaArchiveError(RuntimeError):
    """A local anomaly clip could not be safely archived."""


def candidate_archive_path(
    store: LongitudinalStore, row: Any, *, require_exists: bool = True
) -> Path:
    """Resolve only the canonical elder-scoped archive path from SQLite."""

    relative = Path(str(row["relative_path"]))
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or relative.parts[0] != "anomaly_clips"
        or relative.suffix != ".mp4"
        or relative.stem != str(row["archive_id"])
    ):
        raise MediaArchiveError("candidate archive path is invalid")
    archive_dir = store.elder_dir / "anomaly_clips"
    path = store.elder_dir / relative
    if archive_dir.is_symlink():
        raise MediaArchiveError("candidate archive directory cannot be a symbolic link")
    if archive_dir.parent.resolve() != store.elder_dir.resolve():
        raise MediaArchiveError("candidate archive directory escapes its owner")
    if path.parent.resolve() != archive_dir.resolve():
        raise MediaArchiveError("candidate archive path escapes its owner directory")
    if path.is_symlink():
        raise MediaArchiveError("candidate archive cannot be a symbolic link")
    if require_exists:
        try:
            details = path.stat()
        except FileNotFoundError as error:
            raise MediaArchiveError("candidate archive file is missing") from error
        if not stat.S_ISREG(details.st_mode) or details.st_size <= 0:
            raise MediaArchiveError("candidate archive is not a regular media file")
        if details.st_size != int(row["byte_size"]):
            raise MediaArchiveError("candidate archive size does not match its index")
    return path


def candidate_archive_available(store: LongitudinalStore, row: Any) -> bool:
    try:
        candidate_archive_path(store, row)
        retention_until = _aware_utc(
            datetime.fromisoformat(str(row["retention_until"]))
        )
    except (MediaArchiveError, ValueError):
        return False
    return retention_until > datetime.now(timezone.utc)


def candidate_archive_verified(store: LongitudinalStore, row: Any) -> bool:
    """Check expiry, size, regular-file status and SHA-256 before owner playback."""

    if not candidate_archive_available(store, row):
        return False
    try:
        path = candidate_archive_path(store, row)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except (MediaArchiveError, OSError):
        return False
    return digest == str(row["sha256"])


def archive_candidate_clip(
    store: LongitudinalStore,
    *,
    segment: Any,
    candidate: DomainCandidate,
    pre_seconds: float,
    post_seconds: float,
    retention_days: int,
    maximum_total_bytes: int,
    video_fps: float,
) -> CandidateMediaArchive:
    """Encode one event-bounded audiovisual MP4 and index it after atomic publish."""

    if pre_seconds < 0 or post_seconds <= 0:
        raise ValueError("archive event window must include positive post-event time")
    if retention_days <= 0:
        raise ValueError("archive retention days must be positive")
    if maximum_total_bytes <= 0:
        raise ValueError("archive maximum bytes must be positive")
    if video_fps <= 0:
        raise ValueError("archive video fps must be positive")
    existing = store.fetch_candidate_media_archive(candidate.candidate_id)
    if existing is not None and candidate_archive_available(store, existing):
        return _archive_from_row(existing)
    if existing is not None:
        store.delete_media_archive(str(existing["archive_id"]))

    occurred_at = _aware_utc(candidate.occurred_at)
    segment_started_at = _aware_utc(segment.started_at)
    offset_ms = round((occurred_at - segment_started_at).total_seconds() * 1000)
    if offset_ms < 0 or offset_ms > int(segment.duration_ms):
        raise MediaArchiveError("candidate time falls outside its in-memory segment")
    start_ms = max(0, offset_ms - round(pre_seconds * 1000))
    end_ms = min(int(segment.duration_ms), offset_ms + round(post_seconds * 1000))
    if end_ms <= start_ms:
        raise MediaArchiveError("candidate archive window is empty")

    archive_id = hashlib.sha256(
        (
            f"archive|{candidate.candidate_id}|{segment.segment_id}|"
            f"{start_ms}|{end_ms}"
        ).encode("utf-8")
    ).hexdigest()
    relative_path = f"anomaly_clips/{archive_id}.mp4"
    archive_dir = store.elder_dir / "anomaly_clips"
    if archive_dir.is_symlink():
        raise MediaArchiveError("candidate archive directory cannot be a symbolic link")
    archive_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if archive_dir.is_symlink() or archive_dir.resolve().parent != store.elder_dir.resolve():
        raise MediaArchiveError("candidate archive directory is not owner scoped")
    archive_dir.chmod(0o700)
    final_path = store.elder_dir / relative_path
    temporary_path: Path | None = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            dir=archive_dir,
            prefix=f".{archive_id}.",
            suffix=".mp4",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        _encode_mp4(
            temporary_path,
            segment=segment,
            start_ms=start_ms,
            end_ms=end_ms,
            video_fps=video_fps,
        )
        byte_size = temporary_path.stat().st_size
        if byte_size <= 0:
            raise MediaArchiveError("encoded candidate archive is empty")
        if byte_size > maximum_total_bytes:
            raise MediaArchiveError("candidate archive exceeds the local size limit")
        prune_candidate_archives(
            store,
            now=datetime.now(timezone.utc),
            maximum_total_bytes=maximum_total_bytes,
            incoming_bytes=byte_size,
        )
        temporary_path.chmod(0o600)
        temporary_path.replace(final_path)
        temporary_path = None
        published = True
        final_path.chmod(0o600)
        with final_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        created_at = datetime.now(timezone.utc)
        archive = CandidateMediaArchive(
            archive_id=archive_id,
            candidate_id=candidate.candidate_id,
            segment_id=str(segment.segment_id),
            device_ref=str(segment.device_ref),
            relative_path=relative_path,
            started_at=segment_started_at + timedelta(milliseconds=start_ms),
            ended_at=segment_started_at + timedelta(milliseconds=end_ms),
            sha256=digest,
            byte_size=byte_size,
            created_at=created_at,
            retention_until=created_at + timedelta(days=retention_days),
        )
        try:
            store.record_candidate_media_archive(_archive_row(archive))
        except Exception:
            final_path.unlink(missing_ok=True)
            published = False
            raise
        return archive
    except MediaArchiveError:
        if published:
            final_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        if published:
            final_path.unlink(missing_ok=True)
        raise MediaArchiveError("candidate MP4 encoding failed") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def prune_candidate_archives(
    store: LongitudinalStore,
    *,
    now: datetime,
    maximum_total_bytes: int,
    incoming_bytes: int = 0,
) -> int:
    """Remove expired/corrupt/oldest clips until the configured byte cap fits."""

    if maximum_total_bytes <= 0 or incoming_bytes < 0:
        raise ValueError("archive byte limits are invalid")
    now = _aware_utc(now)
    retained: list[tuple[Any, Path, int]] = []
    removed = 0
    for row in store.fetch_media_archives():
        try:
            path = candidate_archive_path(store, row)
            retention_until = _aware_utc(
                datetime.fromisoformat(str(row["retention_until"]))
            )
        except (MediaArchiveError, ValueError):
            store.delete_media_archive(str(row["archive_id"]))
            removed += 1
            continue
        if retention_until <= now:
            path.unlink(missing_ok=True)
            store.delete_media_archive(str(row["archive_id"]))
            removed += 1
            continue
        retained.append((row, path, int(row["byte_size"])))
    total = sum(item[2] for item in retained)
    for row, path, size in retained:
        if total + incoming_bytes <= maximum_total_bytes:
            break
        path.unlink(missing_ok=True)
        store.delete_media_archive(str(row["archive_id"]))
        total -= size
        removed += 1
    return removed


def _encode_mp4(
    output_path: Path,
    *,
    segment: Any,
    start_ms: int,
    end_ms: int,
    video_fps: float,
) -> None:
    import av
    import cv2
    import numpy as np

    selected_frames = [
        item for item in segment.frames if start_ms <= item.timestamp_ms < end_ms
    ]
    if not selected_frames:
        raise MediaArchiveError("candidate window has no video frames")
    sample_rate = int(segment.audio.sample_rate_hz)
    sample_start = round(start_ms * sample_rate / 1000)
    sample_end = round(end_ms * sample_rate / 1000)
    audio_values = np.asarray(
        segment.audio.samples[sample_start:sample_end], dtype=np.float32
    )
    if audio_values.size == 0:
        raise MediaArchiveError("candidate window has no audio samples")
    width = int(segment.frame_width) - int(segment.frame_width) % 2
    height = int(segment.frame_height) - int(segment.frame_height) % 2
    if width <= 0 or height <= 0:
        raise MediaArchiveError("candidate window has invalid video dimensions")

    rate = Fraction(str(video_fps)).limit_denominator(1000)
    with av.open(
        str(output_path), "w", format="mp4", options={"movflags": "+faststart"}
    ) as output:
        video = output.add_stream("libx264", rate=rate)
        video.width = width
        video.height = height
        video.pix_fmt = "yuv420p"
        video.options = {"crf": "29", "preset": "veryfast"}
        audio = output.add_stream("aac", rate=sample_rate)
        audio.layout = "mono"
        audio.bit_rate = 64_000
        for index, buffered in enumerate(selected_frames):
            pixels = cv2.imdecode(
                np.frombuffer(buffered.jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if pixels is None:
                raise MediaArchiveError("candidate JPEG frame cannot be decoded")
            if pixels.shape[1] != width or pixels.shape[0] != height:
                pixels = cv2.resize(pixels, (width, height))
            frame = av.VideoFrame.from_ndarray(pixels, format="bgr24")
            frame.pts = index
            frame.time_base = Fraction(rate.denominator, rate.numerator)
            for packet in video.encode(frame):
                output.mux(packet)
        for packet in video.encode():
            output.mux(packet)

        pcm = np.rint(np.clip(audio_values, -1.0, 1.0) * 32767).astype(np.int16)
        cursor = 0
        while cursor < pcm.size:
            chunk = np.ascontiguousarray(pcm[cursor : cursor + 1024].reshape(1, -1))
            frame = av.AudioFrame.from_ndarray(chunk, format="s16", layout="mono")
            frame.sample_rate = sample_rate
            frame.pts = cursor
            frame.time_base = Fraction(1, sample_rate)
            for packet in audio.encode(frame):
                output.mux(packet)
            cursor += chunk.shape[1]
        for packet in audio.encode():
            output.mux(packet)


def _archive_row(archive: CandidateMediaArchive) -> dict[str, Any]:
    payload = archive.model_dump(mode="json")
    return {
        "archive_id": archive.archive_id,
        "candidate_id": archive.candidate_id,
        "segment_id": archive.segment_id,
        "device_ref": archive.device_ref,
        "relative_path": archive.relative_path,
        "mime_type": archive.mime_type,
        "started_at": str(payload["started_at"]),
        "ended_at": str(payload["ended_at"]),
        "sha256": archive.sha256,
        "byte_size": archive.byte_size,
        "has_video": 1,
        "has_audio": 1,
        "owner_only": 1,
        "raw_stream_persisted": 0,
        "created_at": str(payload["created_at"]),
        "retention_until": str(payload["retention_until"]),
    }


def _archive_from_row(row: Any) -> CandidateMediaArchive:
    return CandidateMediaArchive(
        archive_id=str(row["archive_id"]),
        candidate_id=str(row["candidate_id"]),
        segment_id=str(row["segment_id"]),
        device_ref=str(row["device_ref"]),
        relative_path=str(row["relative_path"]),
        mime_type=str(row["mime_type"]),
        started_at=datetime.fromisoformat(str(row["started_at"])),
        ended_at=datetime.fromisoformat(str(row["ended_at"])),
        sha256=str(row["sha256"]),
        byte_size=int(row["byte_size"]),
        has_video=bool(row["has_video"]),
        has_audio=bool(row["has_audio"]),
        owner_only=bool(row["owner_only"]),
        raw_stream_persisted=bool(row["raw_stream_persisted"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        retention_until=datetime.fromisoformat(str(row["retention_until"])),
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise MediaArchiveError("archive timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
