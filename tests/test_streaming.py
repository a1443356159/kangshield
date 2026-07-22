from __future__ import annotations

from fractions import Fraction
import wave

import pytest

from kangshield.information.media_probe import probe_media
from kangshield.information.streaming import (
    OpenCVVideoReplay,
    read_container_audio,
    read_pcm_wav,
)


def _write_av_container(
    path,
    *,
    audio_offset_ms: int = 0,
    audio_stream_count: int = 1,
    skip_audio_indices=frozenset(),
    seconds: int = 1,
):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    fps = 10
    sample_rate = 8000
    samples_per_frame = sample_rate // fps
    offset_samples = round(audio_offset_ms * sample_rate / 1000)
    with av.open(str(path), "w", format="matroska") as output:
        video = output.add_stream("ffv1", rate=fps)
        video.width = 64
        video.height = 48
        video.pix_fmt = "yuv420p"
        audio_streams = []
        for _ in range(audio_stream_count):
            audio = output.add_stream("pcm_s16le", rate=sample_rate)
            audio.layout = "mono"
            audio_streams.append(audio)
        for index in range(seconds * fps):
            pixels = np.full((48, 64, 3), index, dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame.pts = index
            video_frame.time_base = Fraction(1, fps)
            for packet in video.encode(video_frame):
                output.mux(packet)

            for stream_index, audio in enumerate(audio_streams):
                if index in skip_audio_indices:
                    continue
                samples = np.full(
                    (1, samples_per_frame),
                    500 + stream_index,
                    dtype=np.int16,
                )
                audio_frame = av.AudioFrame.from_ndarray(
                    samples,
                    format="s16",
                    layout="mono",
                )
                audio_frame.sample_rate = sample_rate
                audio_frame.pts = index * samples_per_frame + offset_samples
                audio_frame.time_base = Fraction(1, sample_rate)
                for packet in audio.encode(audio_frame):
                    output.mux(packet)
        for packet in video.encode():
            output.mux(packet)
        for audio in audio_streams:
            for packet in audio.encode():
                output.mux(packet)


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
    assert audio.start_ms == 0


def test_read_container_audio_resamples_and_applies_positive_pts_offset(tmp_path):
    path = tmp_path / "offset.mkv"
    _write_av_container(path, audio_offset_ms=250)
    probe = probe_media(path, require_audio_track=True)
    assert probe.container_timing is not None
    assert probe.container_timing.audio_minus_video_start_ms == 250.0

    audio = read_container_audio(
        path,
        audio_minus_video_start_ms=250.0,
        target_sample_rate_hz=16000,
        max_duration_s=0.75,
    )

    assert audio.sample_rate_hz == 16000
    assert audio.start_ms == 250
    assert audio.duration_ms == 500
    assert len(audio.samples) == 8000
    assert float(abs(audio.samples).max()) > 0.0


def test_read_container_audio_trims_samples_before_video_zero(tmp_path):
    path = tmp_path / "audio-starts-first.mkv"
    _write_av_container(path)

    audio = read_container_audio(
        path,
        audio_minus_video_start_ms=-250.0,
        target_sample_rate_hz=16000,
        max_duration_s=0.75,
    )

    assert audio.start_ms == 0
    assert audio.duration_ms == 750
    assert len(audio.samples) == 12000


def test_read_container_audio_preserves_packet_pts_gap_as_silence(tmp_path):
    path = tmp_path / "audio-gap.mkv"
    _write_av_container(path, skip_audio_indices={4, 5})

    audio = read_container_audio(
        path,
        audio_minus_video_start_ms=0.0,
        target_sample_rate_hz=16000,
        max_duration_s=1.0,
    )

    assert audio.duration_ms == 1000
    assert len(audio.samples) == 16000
    assert float(abs(audio.samples[7000:9000]).max()) == 0.0
    assert float(abs(audio.samples[:5000]).max()) > 0.0
    assert float(abs(audio.samples[11000:]).max()) > 0.0


@pytest.mark.parametrize("audio_stream_count", [0, 2])
def test_read_container_audio_rejects_missing_or_ambiguous_track(
    tmp_path,
    audio_stream_count,
):
    path = tmp_path / f"audio-count-{audio_stream_count}.mkv"
    _write_av_container(path, audio_stream_count=audio_stream_count)

    with pytest.raises(ValueError, match="exactly one audio stream"):
        read_container_audio(
            path,
            audio_minus_video_start_ms=0.0,
            max_duration_s=1.0,
        )


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
