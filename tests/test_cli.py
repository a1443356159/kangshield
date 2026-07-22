from __future__ import annotations

import json
from pathlib import Path

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


def test_pose_benchmark_parser_defaults_to_both_variants():
    args = build_parser().parse_args(
        ["benchmark-pose-models", "benchmark-cases.json"]
    )
    assert args.command == "benchmark-pose-models"
    assert args.variant is None
    assert args.rtmpose_detection_confidence == 0.05


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
