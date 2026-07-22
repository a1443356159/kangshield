from __future__ import annotations

import json
from pathlib import Path

import pytest

from kangshield.information.cli import main
from kangshield.information.cli import build_parser


SLEEP_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "sleep"
    / "sdnl1-export.synthetic.json"
)


def test_profile_sleep_cli_creates_completed_run(tmp_path, capsys):
    exit_code = main(
        [
            "profile-sleep",
            str(SLEEP_FIXTURE),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--evidence-level",
            "E1",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    manifest_path = Path(output["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output["record_count"] == 2
    assert manifest["status"] == "completed"
    assert manifest["evidence_level"] == "E1"
    assert (manifest_path.parent / "reports" / "sleep-field-profile.json").is_file()


def test_pose_benchmark_parser_freezes_three_variant_defaults():
    args = build_parser().parse_args(
        ["benchmark-pose-models", "benchmark-cases.json"]
    )
    assert args.command == "benchmark-pose-models"
    assert args.variant is None
    assert args.rtmpose_detection_confidence == 0.05
    assert args.torchvision_model.name.endswith("fc266e95.pth")
    assert args.torchvision_policy.name == "v1-m3-torchvision-pose-model.json"
    assert args.torchvision_detection_confidence == 0.5
    assert args.torchvision_min_size == 800
    assert args.torchvision_max_size == 1333


def test_speech_benchmark_parser_freezes_candidate_decoding_defaults():
    args = build_parser().parse_args(
        ["benchmark-speech-models", "benchmark-cases.json"]
    )
    assert args.command == "benchmark-speech-models"
    assert args.variant is None
    assert args.language == "zh"
    assert args.whisper_beam_size == 5
    assert args.whisper_fp16 is None


def test_sleep_route_parser_defaults_to_fail_closed_fixture_inputs():
    args = build_parser().parse_args(
        ["assess-sleep-route", "sleep-export.json"]
    )
    assert args.command == "assess-sleep-route"
    assert args.evidence_level.value == "E1"
    assert args.source_type.value == "fixture"
    assert args.policy.name == "v1-sleep-route-policy.json"
    assert args.mapping_config.name == "sdnl1-field-map.example.json"


def test_media_probe_parser_freezes_packet_scan_and_audio_gate_defaults():
    args = build_parser().parse_args(["probe-media", "capture.mkv"])
    assert args.command == "probe-media"
    assert args.require_audio_track is False
    assert args.max_packets_per_stream == 200_000


def test_multimodal_parser_supports_legacy_wav_and_same_container_audio():
    legacy = build_parser().parse_args(
        ["run-multimodal", "capture.avi", "speech.wav"]
    )
    assert legacy.audio == Path("speech.wav")
    assert legacy.audio_from_video is False

    same_container = build_parser().parse_args(
        ["run-multimodal", "capture.mkv", "--audio-from-video"]
    )
    assert same_container.audio is None
    assert same_container.audio_from_video is True


def test_multimodal_cli_rejects_missing_or_conflicting_audio_selection():
    with pytest.raises(ValueError, match="provide a PCM WAV"):
        main(["run-multimodal", "capture.mkv"])
    with pytest.raises(ValueError, match="do not provide a separate audio"):
        main(
            [
                "run-multimodal",
                "capture.mkv",
                "speech.wav",
                "--audio-from-video",
            ]
        )


def test_m2c_capture_parser_defaults_to_fixture_and_fail_closed_policy():
    args = build_parser().parse_args(
        ["assess-m2c-capture", "capture-manifest.json"]
    )
    assert args.command == "assess-m2c-capture"
    assert args.evidence_level.value == "E1"
    assert args.source_type.value == "fixture"
    assert args.policy.name == "v1-m2c-capture-policy.json"
    assert args.max_packets_per_stream == 200_000
    assert args.require_ready is False


def test_event_evaluation_parser_defaults_to_fixture_and_real_readiness_closed():
    args = build_parser().parse_args(
        ["assess-event-evaluation", "event-evaluation-bundle.json"]
    )
    assert args.command == "assess-event-evaluation"
    assert args.evidence_level.value == "E1"
    assert args.source_type.value == "fixture"
    assert args.policy.name == "v1-g4-event-evaluation-policy.json"
    assert args.require_ready is False


def test_event_bundle_parser_requires_explicit_sensitive_inputs():
    args = build_parser().parse_args(
        [
            "assemble-event-evaluation-bundle",
            "capture.json",
            "readiness.json",
            "readiness-run.json",
            "candidate-policy.json",
            "adjudication.json",
            "--annotation",
            "annotation-a.json",
            "--annotation",
            "annotation-b.json",
            "--prediction-source",
            "yolo.json",
            "yolo-run.json",
            "--output",
            "event-bundle",
        ]
    )
    assert args.command == "assemble-event-evaluation-bundle"
    assert len(args.annotation) == 2
    assert args.prediction_source == [
        [Path("yolo.json"), Path("yolo-run.json")]
    ]
    assert args.evidence_level.value == "E1"
    assert args.source_type.value == "fixture"
    assert args.evaluation_policy.name == "v1-g4-event-evaluation-policy.json"


def test_fall_feature_parser_defaults_to_candidate_and_clean_source():
    args = build_parser().parse_args(
        [
            "benchmark-fall-features",
            "benchmark-cases.json",
            "pose-model-comparison-report.json",
        ]
    )
    assert args.command == "benchmark-fall-features"
    assert args.variant == "rtmpose-m-humanart"
    assert args.config.name == "v1-g4-fall-features.json"
    assert args.model_binding_policy.name == "v1-m3-pose-models.json"
    assert args.torchvision_policy.name == "v1-m3-torchvision-pose-model.json"
    assert args.allow_dirty_source is False


def test_fall_adl_parser_defaults_to_fixed_three_variant_stress_run():
    args = build_parser().parse_args(
        ["benchmark-fall-adl", "fall-adl-cases.json"]
    )
    assert args.command == "benchmark-fall-adl"
    assert args.variant is None
    assert args.config.name == "v1-g4-fall-features.json"
    assert args.model_binding_policy.name == "v1-m3-pose-models.json"
    assert args.pose_sample_fps == 5.0
    assert args.max_duration_s == 30.0
    assert args.torchvision_detection_confidence == 0.5
    assert args.torchvision_min_size == 800
    assert args.torchvision_max_size == 1333


def test_fall_candidate_parser_requires_sources_and_freezes_policy_default():
    args = build_parser().parse_args(
        [
            "benchmark-fall-candidates",
            "--urfd-run",
            "runs/yolo",
            "--urfd-run",
            "runs/rtmpose",
            "--urfd-run",
            "runs/keypointrcnn",
            "--caucafall-run",
            "runs/caucafall",
        ]
    )
    assert args.command == "benchmark-fall-candidates"
    assert len(args.urfd_run) == 3
    assert args.policy.name == "v1-g4-event-candidate-policy.json"
    assert args.benchmark_cases.name == "benchmark-cases.json"
    assert args.allow_dirty_source is False


def test_fall_feature_capture_parser_requires_variant_and_freezes_defaults():
    args = build_parser().parse_args(
        [
            "capture-fall-features",
            "capture-manifest.json",
            "capture-readiness.json",
            "capture-readiness-run.json",
            "--variant",
            "yolo26n-pose",
        ]
    )
    assert args.command == "capture-fall-features"
    assert args.variant == "yolo26n-pose"
    assert args.evidence_level.value == "E1"
    assert args.source_type.value == "fixture"
    assert args.feature_config.name == "v1-g4-fall-features.json"
    assert args.sample_fps == 5.0
    assert args.allow_dirty_readiness is False
    assert args.yolo_model.name == "yolo26n-pose.pt"
    assert args.rtmpose_detection_confidence == 0.05
    assert args.torchvision_model.name.endswith("fc266e95.pth")
    assert args.torchvision_detection_confidence == 0.5


def test_static_home_parser_defaults_to_fixed_three_variant_stress_run():
    args = build_parser().parse_args(
        ["benchmark-static-home", "static-home-cases.json"]
    )
    assert args.command == "benchmark-static-home"
    assert args.variant is None
    assert args.model_binding_policy.name == "v1-m3-pose-models.json"
    assert args.yolo_confidence == 0.35
    assert args.rtmpose_detection_confidence == 0.05
    assert args.torchvision_detection_confidence == 0.5
    assert args.torchvision_min_size == 800
    assert args.torchvision_max_size == 1333
