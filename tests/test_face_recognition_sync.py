from __future__ import annotations

import numpy as np

from kangshield.information.prediction_sync.face_recognition import (
    DetectedFace,
    FaceGallery,
    FaceRecognitionConfig,
    MatchResult,
    PersonObservation,
    RealtimeFaceRecognizer,
    TrackIdentityManager,
    associate_faces_to_people,
    draw_identity_annotations,
)


LANDMARKS = np.asarray(
    [[35, 35], [55, 35], [45, 45], [37, 57], [53, 57]], dtype=np.float32
)


class FakeBackend:
    metadata = {"detector": "fake", "recognizer": "fake"}

    def detect(self, frame):
        return [DetectedFace((20, 20, 80, 80), LANDMARKS, 0.98)]

    def embed(self, frame, face):
        return np.asarray([1.0, 0.0, 0.0], dtype=np.float32)


def test_gallery_round_trip_and_unknown(tmp_path):
    gallery = FaceGallery(
        np.asarray([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
        ["person-1", "person-2"],
        ["One", "Two"],
    )
    destination = tmp_path / "gallery.npz"
    gallery.save(destination)
    loaded = FaceGallery.load(destination)
    assert loaded.match([0.99, 0.01, 0], 0.8).person_id == "person-1"
    assert loaded.match([0, 0, 1], 0.8).status == "unknown"


def test_identity_requires_two_matches():
    manager = TrackIdentityManager(confirmation_matches=2)
    person = PersonObservation(7, (0, 0, 100, 200), 0.9)
    manager.update_people([person], 0)
    match = MatchResult("recognized", "person-1", "One", 0.9, 0.45)
    assert manager.record_match(7, match, 0).state == "face_candidate"
    confirmed = manager.record_match(7, match, 500)
    assert confirmed.state == "face_confirmed"
    assert confirmed.person_id == "person-1"


def test_single_face_is_associated_with_single_person():
    face = DetectedFace((20, 20, 80, 80), LANDMARKS, 0.98)
    person = PersonObservation(7, (0, 0, 100, 200), 0.9)
    associations = associate_faces_to_people([face], [person])
    assert associations.person_to_face == {0: 0}


def test_realtime_recognizer_confirms_and_carries_identity():
    gallery = FaceGallery(np.asarray([[1, 0, 0]], dtype=np.float32), ["p1"], ["Alice"])
    recognizer = RealtimeFaceRecognizer(
        FakeBackend(),
        gallery,
        FaceRecognitionConfig(
            sample_fps=5,
            similarity_threshold=0.45,
            min_face_size=10,
            min_blur_variance=0,
            confirmation_matches=2,
        ),
    )
    frame = np.zeros((240, 160, 3), dtype=np.uint8)
    people = [PersonObservation(7, (0, 0, 100, 220), 0.9)]
    first = recognizer.process_frame(
        frame,
        people,
        timestamp_ms=0,
        frame_number=1,
        primary_track_id=7,
    )
    assert first["primary"]["identity_state"] == "face_candidate"
    second = recognizer.process_frame(
        frame,
        people,
        timestamp_ms=250,
        frame_number=2,
        primary_track_id=7,
    )
    assert second["primary"]["status"] == "recognized"
    assert second["primary"]["name"] == "Alice"
    moved_people = [PersonObservation(7, (10, 5, 120, 225), 0.9)]
    carried = recognizer.process_frame(
        frame,
        moved_people,
        timestamp_ms=300,
        frame_number=3,
        primary_track_id=7,
    )
    assert carried["primary"]["identity_state"] == "track_carried"
    assert carried["primary"]["face_bbox_source"] == "track_cache"
    assert carried["primary"]["face_bbox_xyxy"] == [32.0, 25.0, 98.0, 85.0]
    annotated = draw_identity_annotations(frame, carried)
    assert annotated[25, 32].any()
