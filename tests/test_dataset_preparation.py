from __future__ import annotations

import json
import tarfile
import wave
import zipfile
from io import BytesIO

import pytest

from kangshield.information.dataset_preparation import (
    _normalize_and_validate_fleurs_wav,
    convert_urfd_sequence,
    extract_fleurs_audio,
    read_fleurs_rows,
)


def test_convert_urfd_png_archive_preserves_frame_time_and_phase(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    archive_path = tmp_path / "fall-99-cam0-rgb.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for frame_number, value in enumerate((20, 80, 140), start=1):
            frame = np.full((24, 32, 3), value, dtype=np.uint8)
            ok, encoded = cv2.imencode(".png", frame)
            assert ok
            archive.writestr(
                f"fall-99-cam0-rgb/fall-99-cam0-rgb-{frame_number:03d}.png",
                encoded.tobytes(),
            )
    sync_path = tmp_path / "fall-99-data.csv"
    sync_path.write_text("1,0,1.0\n2,100,1.0\n3,200,1.0\n", encoding="utf-8")
    labels_path = tmp_path / "falls.csv"
    labels_path.write_text(
        "fall-99,1,-1\nfall-99,2,0\nfall-99,3,1\n",
        encoding="utf-8",
    )
    video_path = tmp_path / "fall-99.avi"
    annotation_path = tmp_path / "fall-99.json"

    annotation = convert_urfd_sequence(
        archive_path=archive_path,
        sync_path=sync_path,
        labels_path=labels_path,
        sequence="fall-99",
        video_path=video_path,
        annotation_path=annotation_path,
    )

    capture = cv2.VideoCapture(str(video_path))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 3
    capture.release()
    persisted = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert annotation["fps"] == 10.0
    assert persisted["maximum_replay_alignment_error_ms"] == 0
    assert [item["posture_label"] for item in persisted["frames"]] == [-1, 0, 1]


def test_extract_and_normalize_fleurs_float_wav(tmp_path):
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    source_wav = tmp_path / "source.wav"
    samples = np.linspace(-0.5, 0.5, 1600, dtype=np.float32)
    sf.write(str(source_wav), samples, 16000, subtype="FLOAT", format="WAV")
    archive_path = tmp_path / "dev.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source_wav, arcname="dev/123.wav")
    tsv_path = tmp_path / "dev.tsv"
    tsv_path.write_text(
        "1\t123.wav\t你好，世界。\t你 好 世 界\t你 | 好 | 世 | 界 |\t1600\tFEMALE\n",
        encoding="utf-8",
    )

    rows = read_fleurs_rows(tsv_path)
    extracted = extract_fleurs_audio(
        archive_path=archive_path,
        filenames={"123.wav"},
        output_dir=tmp_path / "audio",
    )
    metadata = _normalize_and_validate_fleurs_wav(
        extracted["123.wav"],
        expected_samples=rows["123.wav"]["num_samples"],
    )

    with wave.open(str(extracted["123.wav"]), "rb") as stream:
        assert stream.getsampwidth() == 2
        assert stream.getnchannels() == 1
        assert stream.getnframes() == 1600
    assert metadata["duration_ms"] == 100
