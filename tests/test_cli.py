from __future__ import annotations

import json
from pathlib import Path

from kangshield.information.cli import main


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
