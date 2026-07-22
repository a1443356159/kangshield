.PHONY: test info-fixtures prepare-mm-models prepare-mm-smoke submit-mm-smoke prepare-m2b-data submit-m2b-benchmark prepare-m3-pose-models submit-m3-pose-comparison

PYTHON ?= python3
KANG_VIDEO_INPUT ?= $(CURDIR)/data/raw/public-smoke/ultralytics-bus-replay.avi
KANG_AUDIO_INPUT ?= $(CURDIR)/data/raw/public-smoke/funasr-asr-example-zh.wav
KANG_M2B_CASES ?= $(CURDIR)/data/processed/v1-m2b/benchmark-cases.json

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

prepare-m2b-data:
	$(PYTHON) scripts/prepare_v1_m2b_data.py --accept-urfd-noncommercial-license

submit-m2b-benchmark:
	test -f "$(KANG_M2B_CASES)"
	sbatch --export=ALL,KANG_DATASET_CASES="$(KANG_M2B_CASES)" scripts/slurm/v1_m2b_dataset_benchmark.sbatch

prepare-m3-pose-models:
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py

submit-m3-pose-comparison:
	test -f "$(KANG_M2B_CASES)"
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py --offline
	sbatch --export=ALL,KANG_DATASET_CASES="$(KANG_M2B_CASES)" scripts/slurm/v1_m3_pose_comparison.sbatch
