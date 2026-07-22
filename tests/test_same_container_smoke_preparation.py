from __future__ import annotations

import wave

import pytest

from kangshield.information.media_probe import probe_media
from kangshield.information.streaming import read_container_audio
from scripts.prepare_v1_m2a_same_container_smoke import build_same_container_smoke


def _write_video(path) -> None:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer unavailable")
    for value in range(10):
        writer.write(np.full((48, 64, 3), value * 10, dtype=np.uint8))
    writer.release()


def _write_audio(path) -> None:
    np = pytest.importorskip("numpy")
    samples = (
        np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 1000
    ).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(samples.tobytes())


def test_public_smoke_composer_preserves_requested_audio_pts_offset(tmp_path):
    video_path = tmp_path / "video.avi"
    audio_path = tmp_path / "speech.wav"
    output_path = tmp_path / "combined.mkv"
    second_output_path = tmp_path / "combined-again.mkv"
    _write_video(video_path)
    _write_audio(audio_path)

    receipt = build_same_container_smoke(
        video_path=video_path,
        audio_path=audio_path,
        output_path=output_path,
        audio_offset_ms=250,
    )
    second_receipt = build_same_container_smoke(
        video_path=video_path,
        audio_path=audio_path,
        output_path=second_output_path,
        audio_offset_ms=250,
    )
    probe = probe_media(output_path, require_audio_track=True)
    decoded = read_container_audio(
        output_path,
        audio_minus_video_start_ms=250.0,
        max_duration_s=0.75,
    )

    assert receipt["audio_offset_ms"] == 250
    assert receipt["video_frame_count"] == 10
    assert receipt["audio_sample_count"] == 16000
    assert receipt["synthetic_alignment"] is True
    assert receipt["bitexact_mux"] is True
    assert receipt["output_sha256"] == second_receipt["output_sha256"]
    assert probe.container_timing is not None
    assert probe.container_timing.audio_minus_video_start_ms == 250.0
    assert decoded.start_ms == 250
    assert decoded.duration_ms == 500
    assert len(decoded.samples) == 8000
