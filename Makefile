.PHONY: test info-fixtures prepare-mm-models prepare-mm-smoke prepare-mm-container-smoke prepare-m2c-timing-fixture prepare-m2c-capture-fixture assess-m2c-capture-fixture prepare-g4-event-evaluation-fixture assess-g4-event-evaluation-fixture prepare-g4-candidate-export-fixture assess-g4-candidate-export-fixture submit-g4-feature-capture-smoke submit-mm-smoke submit-mm-container-smoke prepare-m2b-data submit-m2b-benchmark prepare-m3-pose-models submit-m3-pose-comparison prepare-m3-speech-models submit-m3-speech-comparison prepare-g4-caucafall submit-g4-adl-benchmark benchmark-g4-fall-candidates prepare-g4-static-home submit-g4-static-home-benchmark

PYTHON ?= python3
KANG_VIDEO_INPUT ?= $(CURDIR)/data/raw/public-smoke/ultralytics-bus-replay.avi
KANG_AUDIO_INPUT ?= $(CURDIR)/data/raw/public-smoke/funasr-asr-example-zh.wav
KANG_AV_INPUT ?= $(CURDIR)/data/raw/public-smoke/v1-m2a-public-av-offset-250ms.mkv
KANG_AV_SOURCE_TYPE ?= fixture
KANG_AV_MAX_DURATION_S ?= 6
KANG_M2B_CASES ?= $(CURDIR)/data/processed/v1-m2b/benchmark-cases.json
KANG_G4_ADL_CASES ?= $(CURDIR)/data/processed/v1-g4-caucafall/fall-adl-cases.json
KANG_G4_STATIC_HOME_CASES ?= $(CURDIR)/data/processed/v1-g4-openimages-static-home/static-home-cases.json
KANG_M2C_CAPTURE_MANIFEST ?= $(CURDIR)/data/raw/public-smoke/v1-m2c-capture/capture-manifest.json
KANG_G4_EVENT_BUNDLE ?= $(CURDIR)/data/raw/public-smoke/v1-g4-event-evaluation/event-evaluation-bundle.json
KANG_G4_CANDIDATE_EXPORT_BUNDLE ?= $(CURDIR)/data/raw/public-smoke/v1-g4-candidate-export/event-evaluation-bundle.json
KANG_G4_FEATURE_CAPTURE_MANIFEST ?= $(CURDIR)/data/raw/public-smoke/v1-g4-candidate-export/capture/capture-manifest.json
KANG_G4_FEATURE_CAPTURE_READINESS ?= $(CURDIR)/data/raw/public-smoke/v1-g4-candidate-export/evidence/m2c-capture-readiness.json
KANG_G4_FEATURE_CAPTURE_READINESS_RUN ?= $(CURDIR)/data/raw/public-smoke/v1-g4-candidate-export/evidence/m2c-capture-run-manifest.json
KANG_G4_URFD_YOLO_RUN ?=
KANG_G4_URFD_RTMPOSE_RUN ?=
KANG_G4_URFD_KEYPOINTRCNN_RUN ?=
KANG_G4_CAUCAFALL_RUN ?=

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

info-fixtures:
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli inspect-ezviz tests/fixtures/ezviz/device-list.synthetic.json --evidence-level E1
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli profile-sleep tests/fixtures/sleep/sdnl1-export.synthetic.json --evidence-level E1
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli assess-sleep-route tests/fixtures/sleep/sdnl1-export.synthetic.json --evidence-level E1

prepare-mm-models:
	$(PYTHON) scripts/prepare_multimodal_models.py

prepare-mm-smoke:
	$(PYTHON) scripts/prepare_public_smoke_inputs.py

prepare-mm-container-smoke:
	test -f "$(KANG_VIDEO_INPUT)"
	test -f "$(KANG_AUDIO_INPUT)"
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m2a_same_container_smoke.py --video "$(KANG_VIDEO_INPUT)" --audio "$(KANG_AUDIO_INPUT)" --output "$(KANG_AV_INPUT)" --force

prepare-m2c-timing-fixture:
	$(PYTHON) scripts/prepare_v1_m2c_timing_fixture.py --force

prepare-m2c-capture-fixture: prepare-m2c-timing-fixture
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m2c_capture_fixture.py --force

assess-m2c-capture-fixture:
	test -f "$(KANG_M2C_CAPTURE_MANIFEST)"
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli assess-m2c-capture "$(KANG_M2C_CAPTURE_MANIFEST)" --source-type fixture --evidence-level E1

prepare-g4-event-evaluation-fixture: prepare-m2c-timing-fixture
	PYTHONPATH=src:. $(PYTHON) scripts/prepare_v1_g4_event_evaluation_fixture.py --force

assess-g4-event-evaluation-fixture:
	test -f "$(KANG_G4_EVENT_BUNDLE)"
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli assess-event-evaluation "$(KANG_G4_EVENT_BUNDLE)" --source-type fixture --evidence-level E1

prepare-g4-candidate-export-fixture: prepare-m2c-timing-fixture
	PYTHONPATH=src:. $(PYTHON) scripts/prepare_v1_g4_candidate_export_fixture.py --force

assess-g4-candidate-export-fixture:
	test -f "$(KANG_G4_CANDIDATE_EXPORT_BUNDLE)"
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli assess-event-evaluation "$(KANG_G4_CANDIDATE_EXPORT_BUNDLE)" --source-type fixture --evidence-level E1

submit-g4-feature-capture-smoke:
	test -f "$(KANG_G4_FEATURE_CAPTURE_MANIFEST)"
	test -f "$(KANG_G4_FEATURE_CAPTURE_READINESS)"
	test -f "$(KANG_G4_FEATURE_CAPTURE_READINESS_RUN)"
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py --offline
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m3_torchvision_pose_model.py --offline
	sbatch --export=ALL,KANG_CAPTURE_MANIFEST="$(KANG_G4_FEATURE_CAPTURE_MANIFEST)",KANG_CAPTURE_READINESS="$(KANG_G4_FEATURE_CAPTURE_READINESS)",KANG_CAPTURE_READINESS_RUN="$(KANG_G4_FEATURE_CAPTURE_READINESS_RUN)" scripts/slurm/v1_g4_feature_capture_smoke.sbatch

submit-mm-smoke:
	test -f "$(KANG_VIDEO_INPUT)"
	test -f "$(KANG_AUDIO_INPUT)"
	sbatch --export=ALL,KANG_VIDEO_INPUT="$(KANG_VIDEO_INPUT)",KANG_AUDIO_INPUT="$(KANG_AUDIO_INPUT)" scripts/slurm/v1_multimodal_smoke.sbatch

submit-mm-container-smoke:
	test -f "$(KANG_AV_INPUT)"
	sbatch --export=ALL,KANG_VIDEO_INPUT="$(KANG_AV_INPUT)",KANG_AUDIO_INPUT=,KANG_AUDIO_FROM_VIDEO=1,KANG_SOURCE_TYPE="$(KANG_AV_SOURCE_TYPE)",KANG_MAX_DURATION_S="$(KANG_AV_MAX_DURATION_S)" scripts/slurm/v1_multimodal_smoke.sbatch

prepare-m2b-data:
	$(PYTHON) scripts/prepare_v1_m2b_data.py --accept-urfd-noncommercial-license

submit-m2b-benchmark:
	test -f "$(KANG_M2B_CASES)"
	sbatch --export=ALL,KANG_DATASET_CASES="$(KANG_M2B_CASES)" scripts/slurm/v1_m2b_dataset_benchmark.sbatch

prepare-m3-pose-models:
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m3_torchvision_pose_model.py

submit-m3-pose-comparison:
	test -f "$(KANG_M2B_CASES)"
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py --offline
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m3_torchvision_pose_model.py --offline
	sbatch --export=ALL,KANG_DATASET_CASES="$(KANG_M2B_CASES)" scripts/slurm/v1_m3_pose_comparison.sbatch

prepare-m3-speech-models:
	$(PYTHON) scripts/prepare_v1_m3_speech_models.py

submit-m3-speech-comparison:
	test -f "$(KANG_M2B_CASES)"
	$(PYTHON) scripts/prepare_v1_m3_speech_models.py --offline
	sbatch --export=ALL,KANG_DATASET_CASES="$(KANG_M2B_CASES)" scripts/slurm/v1_m3_speech_comparison.sbatch

prepare-g4-caucafall:
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_g4_caucafall_data.py

submit-g4-adl-benchmark:
	test -f "$(KANG_G4_ADL_CASES)"
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py --offline
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m3_torchvision_pose_model.py --offline
	sbatch --export=ALL,KANG_FALL_ADL_CASES="$(KANG_G4_ADL_CASES)" scripts/slurm/v1_g4_fall_adl_benchmark.sbatch

benchmark-g4-fall-candidates:
	test -d "$(KANG_G4_URFD_YOLO_RUN)"
	test -d "$(KANG_G4_URFD_RTMPOSE_RUN)"
	test -d "$(KANG_G4_URFD_KEYPOINTRCNN_RUN)"
	test -d "$(KANG_G4_CAUCAFALL_RUN)"
	PYTHONPATH=src $(PYTHON) -m kangshield.information.cli benchmark-fall-candidates --urfd-run "$(KANG_G4_URFD_YOLO_RUN)" --urfd-run "$(KANG_G4_URFD_RTMPOSE_RUN)" --urfd-run "$(KANG_G4_URFD_KEYPOINTRCNN_RUN)" --caucafall-run "$(KANG_G4_CAUCAFALL_RUN)" --benchmark-cases "$(KANG_M2B_CASES)"

prepare-g4-static-home:
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_g4_openimages_data.py

submit-g4-static-home-benchmark:
	test -f "$(KANG_G4_STATIC_HOME_CASES)"
	$(PYTHON) scripts/prepare_v1_m3_pose_models.py --offline
	PYTHONPATH=src $(PYTHON) scripts/prepare_v1_m3_torchvision_pose_model.py --offline
	sbatch --export=ALL,KANG_STATIC_HOME_CASES="$(KANG_G4_STATIC_HOME_CASES)" scripts/slurm/v1_g4_static_home_benchmark.sbatch
