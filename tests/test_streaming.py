from __future__ import annotations

import wave

import pytest

from kangshield.information.streaming import OpenCVVideoReplay, read_pcm_wav


def test_read_pcm_wav_downmixes_and_resamples(tmp_path):
    np = pytest.importorskip("numpy")
    path = tmp_path / "stereo.wav"
    left = np.full(8000, 1000, dtype="<i2")
    right = np.full(8000, -1000, dtype="<i2")
    interleaved = np.column_stack([left, right]).reshape(-1)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(interleaved.tobytes())

    audio = read_pcm_wav(path, target_sample_rate_hz=16000)

    assert audio.sample_rate_hz == 16000
    assert audio.duration_ms == 1000
    assert len(audio.samples) == 16000
    assert float(abs(audio.samples).max()) < 1e-6


def test_opencv_video_replay_emits_timestamped_samples(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    path = tmp_path / "stream.avi"
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10,
        (64, 48),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer unavailable")
    for value in range(20):
        writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
    writer.release()

    packets = list(OpenCVVideoReplay(path, sample_fps=2.0))

    assert [packet.timestamp_ms for packet in packets] == [0, 500, 1000, 1500]
    assert [packet.frame_index for packet in packets] == [0, 5, 10, 15]
