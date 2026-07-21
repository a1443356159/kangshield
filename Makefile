.PHONY: test info-fixtures

test:
	PYTHONPATH=src python3 -m pytest -q

info-fixtures:
	PYTHONPATH=src python3 -m kangshield.information.cli inspect-ezviz tests/fixtures/ezviz/device-list.synthetic.json --evidence-level E1
	PYTHONPATH=src python3 -m kangshield.information.cli profile-sleep tests/fixtures/sleep/sdnl1-export.synthetic.json --evidence-level E1
