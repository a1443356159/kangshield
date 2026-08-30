from __future__ import annotations

import json

import pytest

from kangshield.information.cli import build_parser, main
from kangshield.information.longitudinal.store import LongitudinalStore


def test_cli_exposes_only_final_product_commands():
    parser = build_parser()
    choices = next(
        action.choices
        for action in parser._actions
        if getattr(action, "choices", None)
    )
    assert set(choices) == {
        "run-edge-monitor",
        "serve-product",
        "export-product-report",
        "delete-product-data",
    }


def test_edge_monitor_defaults_to_no_local_media_policy():
    args = build_parser().parse_args(
        ["run-edge-monitor", "--elder-ref", "elder-a", "--device-ref", "c6c-a"]
    )
    assert args.provider == "endpoint_env"
    assert args.max_segments == 0
    assert args.edge_policy.name == "v2-edge-segment-policy.json"
    assert args.evidence_level.value == "E2"


def test_product_parser_enables_cloud_playback_automatically_for_ezviz():
    args = build_parser().parse_args(
        ["serve-product", "--elder-ref", "elder-a", "--device-ref", "c6c-a"]
    )
    assert args.host == "127.0.0.1"
    assert args.cloud_playback_provider == "auto"
    assert args.continuous is False


def test_delete_product_data_requires_exact_confirmation(tmp_path, capsys):
    with LongitudinalStore("elder-a", root=tmp_path) as store:
        assert store.db_path.is_file()
    with pytest.raises(ValueError, match="exactly match"):
        main(
            [
                "delete-product-data",
                "--elder-ref",
                "elder-a",
                "--confirm-ref",
                "wrong",
                "--store-root",
                str(tmp_path),
            ]
        )
    assert main(
        [
            "delete-product-data",
            "--elder-ref",
            "elder-a",
            "--confirm-ref",
            "elder-a",
            "--store-root",
            str(tmp_path),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True
    assert not (tmp_path / "elder-a").exists()
