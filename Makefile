.PHONY: test info-fixtures prepare-mm-models prepare-mm-smoke submit-mm-smoke

PYTHON ?= python3
KANG_VIDEO_INPUT ?= $(CURDIR)/data/raw/public-smoke/ultralytics-bus-replay.avi
KANG_AUDIO_INPUT ?= $(CURDIR)/data/raw/public-smoke/funasr-asr-example-zh.wav

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

info-fixtures:
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli inspect-ezviz tests/fixtures/ezviz/device-list.synthetic.json --evidence-level E1
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli profile-sleep tests/fixtures/sleep/sdnl1-export.synthetic.json --evidence-level E1

prepare-mm-models:
	$(PYTHON) scripts/prepare_multimodal_models.py

prepare-mm-smoke:
	$(PYTHON) scripts/prepare_public_smoke_inputs.py

submit-mm-smoke:
	test -f "$(KANG_VIDEO_INPUT)"
	test -f "$(KANG_AUDIO_INPUT)"
	sbatch --export=ALL,KANG_VIDEO_INPUT="$(KANG_VIDEO_INPUT)",KANG_AUDIO_INPUT="$(KANG_AUDIO_INPUT)" scripts/slurm/v1_multimodal_smoke.sbatch
