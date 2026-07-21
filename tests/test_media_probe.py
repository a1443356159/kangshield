from __future__ import annotations

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
    assert report.technical_metadata["audio_track_status"] == "not_inspected_by_opencv"
