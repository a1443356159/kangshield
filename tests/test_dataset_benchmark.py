from __future__ import annotations

import json

from kangshield.information.artifacts import RunArtifacts
from kangshield.information.contracts import (
    DatasetBenchmarkCase,
    EvidenceLevel,
    FeatureEvent,
    MultimodalPipelineReport,
    PrivacyLevel,
    TimeRange,
)
from kangshield.information.dataset_benchmark import (
    character_error_rate,
    evaluate_dataset_case,
    levenshtein_distance,
    normalize_transcript,
)


def test_transcript_normalization_and_character_error_rate():
    assert normalize_transcript("摩尔多瓦 (Moldova) 的主要宗教。") == (
        "摩尔多瓦moldova的主要宗教"
    )
    assert levenshtein_distance("你好世界", "你好世") == 1
    edits, reference_length, rate = character_error_rate("你好，世界。", "你好世")
    assert (edits, reference_length, rate) == (1, 4, 0.25)


def test_case_evaluation_aligns_phases_and_omits_transcript_text(tmp_path):
    annotation_path = tmp_path / "annotation.json"
    annotation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "frames": [
                    {"replay_timestamp_ms": 0, "posture_label": -1},
                    {"replay_timestamp_ms": 500, "posture_label": 0},
                ],
            }
        ),
        encoding="utf-8",
    )
    case = DatasetBenchmarkCase(
        case_id="case-1",
        pairing_kind="cross_dataset_synthetic_common_zero",
        video_path="video.avi",
        audio_path="audio.wav",
        annotation_path="annotation.json",
        video_dataset="urfd",
        video_sequence="fall-01",
        video_class="fall",
        audio_dataset="fleurs-cmn-hans-cn",
        audio_sample="123.wav",
        audio_gender="female",
        audio_duration_ms=1000,
        reference_transcript="你好，世界。",
    )
    with RunArtifacts(
        tmp_path / "runs",
        stage="test-dataset-case",
        evidence_level=EvidenceLevel.E1,
        project_dir=tmp_path,
    ) as run:
        for sequence, (timestamp_ms, track_id) in enumerate(((0, 7), (500, None))):
            run.record_feature(
                FeatureEvent(
                    feature_id=f"pose-{sequence}",
                    observation_id="video-observation",
                    feature_type="video.pose_frame",
                    time_range=TimeRange(
                        start_ms=timestamp_ms,
                        end_ms=timestamp_ms + 200,
                    ),
                    value={
                        "person_count": 1,
                        "detections": [
                            {
                                "bbox_xyxy": [0.0, 0.0, 20.0, 40.0],
                                "track_id": track_id,
                            }
                        ],
                    },
                    quality=0.75,
                    extractor_name="fake-pose",
                    extractor_version="test",
                    privacy_level=PrivacyLevel.DERIVED_SENSITIVE,
                )
            )
        run.record_feature(
            FeatureEvent(
                feature_id="speech-1",
                observation_id="audio-observation",
                feature_type="audio.speech_segment",
                time_range=TimeRange(start_ms=100, end_ms=600),
                value={"speech_detected": True},
                extractor_name="fake-vad",
                extractor_version="test",
            )
        )
        run.record_feature(
            FeatureEvent(
                feature_id="transcript-1",
                observation_id="audio-observation",
                feature_type="language.transcript_segment",
                time_range=TimeRange(start_ms=100, end_ms=600),
                value={"text": "你好世界", "language": "zh"},
                extractor_name="fake-asr",
                extractor_version="test",
            )
        )
        pipeline_report = MultimodalPipelineReport(
            pipeline_version="test",
            video_asset_id="video",
            audio_asset_id="audio",
            model_bindings=[],
            duration_ms=1000,
            sampled_video_frames=2,
            pose_frames_with_people=2,
            pose_detection_count=2,
            speech_segment_count=1,
            transcript_segment_count=1,
            multimodal_window_count=1,
            realtime_factors={"processing_end_to_end": 0.2},
        )
        evaluation = evaluate_dataset_case(
            case=case,
            run=run,
            annotation_path=annotation_path,
            pipeline_report=pipeline_report,
        )

    serialized = evaluation.model_dump_json()
    assert evaluation.pose_frame_coverage == 1.0
    assert evaluation.pose_tracking_coverage == 0.5
    assert evaluation.phase_metrics["not_lying"].sampled_frames == 1
    assert evaluation.phase_metrics["falling_transition"].sampled_frames == 1
    assert evaluation.speech_coverage == 0.5
    assert evaluation.character_error_rate == 0.0
    assert evaluation.transcript_exact_match is True
    assert "你好世界" not in serialized
