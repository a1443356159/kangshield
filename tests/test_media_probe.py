from __future__ import annotations

from fractions import Fraction
import wave

import pytest

from kangshield.information.contracts import (
    EvidenceLevel,
    Modality,
    QualityStatus,
)
from kangshield.information.media_probe import probe_media


def _write_wav(path, sample_rate: int = 8000, seconds: int = 1) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * sample_rate * seconds)


def _write_av_container(path, *, seconds: int = 1) -> None:
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    fps = 10
    sample_rate = 8000
    samples_per_frame = sample_rate // fps
    with av.open(str(path), "w", format="matroska") as output:
        output.metadata["title"] = "synthetic-sensitive-title"
        video = output.add_stream("ffv1", rate=fps)
        video.width = 64
        video.height = 48
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("pcm_s16le", rate=sample_rate)
        audio.layout = "mono"
        for index in range(seconds * fps):
            pixels = np.full((48, 64, 3), index % 255, dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame.pts = index
            video_frame.time_base = Fraction(1, fps)
            for packet in video.encode(video_frame):
                output.mux(packet)

            samples = np.zeros((1, samples_per_frame), dtype=np.int16)
            audio_frame = av.AudioFrame.from_ndarray(
                samples, format="s16", layout="mono"
            )
            audio_frame.sample_rate = sample_rate
            audio_frame.pts = index * samples_per_frame
            audio_frame.time_base = Fraction(1, sample_rate)
            for packet in audio.encode(audio_frame):
                output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
        for packet in audio.encode():
            output.mux(packet)


def test_probe_wav_records_stable_facts_without_capture_time(tmp_path):
    path = tmp_path / "consented-test.wav"
    _write_wav(path)

    report = probe_media(path, evidence_level=EvidenceLevel.E2)

    assert report.asset.modality is Modality.AUDIO
    assert report.asset.evidence_level is EvidenceLevel.E2
    assert report.asset.uri.startswith("local-file://asset_")
    assert report.asset.uri.endswith(".wav")
    assert "consented-test" not in report.asset.uri
    assert report.asset.captured_start_at is None
    assert report.asset.metadata["file_mtime_is_capture_time"] is False
    assert report.technical_metadata["sample_rate_hz"] == 8000
    assert report.technical_metadata["channels"] == 1
    assert report.technical_metadata["duration_s"] == 1.0
    assert report.observation.quality_status is QualityStatus.PASS


def test_probe_unknown_file_is_explicitly_unknown(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"not media")

    report = probe_media(path)

    assert report.asset.modality is Modality.UNKNOWN
    assert report.observation.quality_status is QualityStatus.PARTIAL
    assert report.issues[0].code == "unsupported_media_type"


def test_probe_video_with_opencv_when_available(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    path = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer unavailable")
    for value in range(10):
        writer.write(np.full((48, 64, 3), value * 20, dtype=np.uint8))
    writer.release()

    report = probe_media(path)

    assert report.technical_metadata["width"] == 64
    assert report.technical_metadata["height"] == 48
    assert report.technical_metadata["fps"] == 10.0
    assert report.technical_metadata["sampled_frame_count"] == 5
    assert report.technical_metadata["audio_track_status"] == "absent"
    assert report.container_timing is not None
    assert report.container_timing.video_stream_count == 1
    assert report.container_timing.audio_stream_count == 0
    assert report.observation.quality_status is QualityStatus.PASS


def test_probe_container_records_audio_video_pts_without_metadata_values(tmp_path):
    path = tmp_path / "private-source-name.mkv"
    _write_av_container(path)

    report = probe_media(path, require_audio_track=True)

    timing = report.container_timing
    assert timing is not None
    assert timing.backend == "pyav"
    assert timing.same_container_av is True
    assert timing.video_track_status == "present"
    assert timing.audio_track_status == "present"
    assert timing.audio_minus_video_start_ms == 0.0
    assert timing.audio_minus_video_end_ms == 0.0
    assert timing.duration_delta_ms == 0.0
    assert timing.drift_estimate_available is False
    assert timing.metadata_key_count >= 1
    assert timing.metadata_values_persisted is False
    assert timing.source_path_persisted is False
    assert {stream.time_base for stream in timing.streams} == {"1/1000"}
    assert {stream.packet_count for stream in timing.streams} == {10}
    assert all(stream.missing_pts_count == 0 for stream in timing.streams)
    assert all(stream.scan_truncated is False for stream in timing.streams)
    serialized = report.model_dump_json()
    assert "private-source-name" not in serialized
    assert "synthetic-sensitive-title" not in serialized
    assert report.observation.quality_status is QualityStatus.PASS


def test_required_audio_and_packet_scan_limit_are_fail_closed(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    path = tmp_path / "video-only.avi"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer unavailable")
    for _ in range(5):
        writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()

    missing = probe_media(path, require_audio_track=True)
    assert missing.observation.quality_status is QualityStatus.FAIL
    assert "required_audio_track_missing" in {
        issue.code for issue in missing.issues
    }

    truncated = probe_media(path, packet_scan_limit_per_stream=2)
    assert truncated.container_timing is not None
    assert truncated.container_timing.streams[0].packet_count == 2
    assert truncated.container_timing.streams[0].scan_truncated is True
    assert truncated.observation.quality_status is QualityStatus.PARTIAL
    assert "container_packet_scan_truncated" in {
        issue.code for issue in truncated.issues
    }


def test_packet_scan_limit_must_be_positive(tmp_path):
    path = tmp_path / "audio.wav"
    _write_wav(path)

    with pytest.raises(ValueError, match="packet_scan_limit_per_stream"):
        probe_media(path, packet_scan_limit_per_stream=0)
