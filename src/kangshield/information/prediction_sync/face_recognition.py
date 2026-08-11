#!/usr/bin/env python3
"""Local face-whitelist recognition for the live fall-detection pipeline.

The implementation is adapted from KangShield's RetinaFace + ArcFace module.
It deliberately separates face identity from temporary person track IDs and
keeps all models, embeddings and results on the local host.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import cv2
import numpy as np


RETINAFACE_WEIGHT_NAME = "detection_Resnet50_Final.pth"
ARCFACE_WEIGHT_NAME = "recognition_arcface_ir_se50.pth"
GALLERY_SCHEMA_VERSION = "kangshield-face-gallery-v1"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class DetectedFace:
    bbox_xyxy: tuple[float, float, float, float]
    landmarks_xy: np.ndarray
    detection_score: float

    def __post_init__(self) -> None:
        landmarks = np.asarray(self.landmarks_xy, dtype=np.float32)
        if landmarks.shape != (5, 2) or not np.isfinite(landmarks).all():
            raise ValueError("face landmarks must contain five finite points")
        if len(self.bbox_xyxy) != 4 or not np.isfinite(self.bbox_xyxy).all():
            raise ValueError("face bbox must contain four finite values")
        if not 0.0 <= self.detection_score <= 1.0:
            raise ValueError("face detection score must be between zero and one")
        object.__setattr__(self, "landmarks_xy", landmarks)


@dataclass(frozen=True)
class PersonObservation:
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float | None


@dataclass(frozen=True)
class MatchResult:
    status: str
    person_id: str | None
    name: str | None
    similarity: float
    threshold: float


@dataclass(frozen=True)
class EnrollmentIssue:
    person_id: str
    image_name: str
    reason: str


class FaceBackend(Protocol):
    @property
    def metadata(self) -> dict[str, Any]: ...

    def detect(self, frame: Any) -> list[DetectedFace]: ...

    def embed(self, frame: Any, face: DetectedFace) -> np.ndarray: ...


def l2_normalize(vector: Any) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("face embedding must be non-empty and finite")
    norm = float(np.linalg.norm(values))
    if norm <= 1e-12:
        raise ValueError("face embedding norm is zero")
    return np.ascontiguousarray(values / norm, dtype=np.float32)


def align_face_112(frame: Any, landmarks_xy: Any) -> np.ndarray:
    source = np.asarray(landmarks_xy, dtype=np.float32)
    if source.shape != (5, 2) or not np.isfinite(source).all():
        raise ValueError("five finite landmarks are required for alignment")
    destination = np.asarray(
        [
            [38.2946, 51.6963],
            [73.5318, 51.5014],
            [56.0252, 71.7366],
            [41.5493, 92.3655],
            [70.7299, 92.2041],
        ],
        dtype=np.float32,
    )
    transform, _ = cv2.estimateAffinePartial2D(source, destination, method=cv2.LMEDS)
    if transform is None or not np.isfinite(transform).all():
        raise ValueError("face alignment transform could not be estimated")
    return cv2.warpAffine(
        np.asarray(frame),
        transform,
        (112, 112),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def _safe_load_state(torch_module: Any, path: Path, device: Any) -> OrderedDict:
    state = torch_module.load(str(path), map_location=device, weights_only=True)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    if not isinstance(state, (dict, OrderedDict)):
        raise ValueError(f"model checkpoint is not a tensor state dict: {path}")
    cleaned = OrderedDict()
    for key, value in state.items():
        name = str(key)
        cleaned[name[7:] if name.startswith("module.") else name] = value
    return cleaned


class FaceXLibRetinaArcBackend:
    """RetinaFace-R50 detection and ArcFace IR-SE50 recognition on Torch."""

    def __init__(
        self,
        model_dir: Path,
        *,
        device: str = "auto",
        detection_threshold: float = 0.7,
        detector_max_side: int = 1280,
    ) -> None:
        if not 0.0 < detection_threshold < 1.0:
            raise ValueError("detection_threshold must be between zero and one")
        if detector_max_side < 320:
            raise ValueError("detector_max_side must be at least 320")
        try:
            import torch
            from facexlib.detection.retinaface import RetinaFace
            from facexlib.recognition.arcface_arch import Backbone
        except ImportError as error:
            raise RuntimeError(
                "Torch, TorchVision and facexlib are required for face recognition"
            ) from error

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested for face recognition but is unavailable")
        self._torch = torch
        self.device = torch.device(device)
        self.detection_threshold = float(detection_threshold)
        self.detector_max_side = int(detector_max_side)

        root = Path(model_dir)
        detection_path = root / RETINAFACE_WEIGHT_NAME
        recognition_path = root / ARCFACE_WEIGHT_NAME
        missing = [str(path) for path in (detection_path, recognition_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError("face model weights are missing: " + ", ".join(missing))

        detector = RetinaFace(
            network_name="resnet50",
            half=False,
            phase="test",
            device=self.device,
        )
        detector.load_state_dict(
            _safe_load_state(torch, detection_path, self.device), strict=True
        )
        detector.eval().to(self.device)
        recognizer = Backbone(num_layers=50, drop_ratio=0.6, mode="ir_se")
        recognizer.load_state_dict(
            _safe_load_state(torch, recognition_path, self.device), strict=True
        )
        recognizer.eval().to(self.device)
        self._detector = detector
        self._recognizer = recognizer
        self._metadata = {
            "detector": "facexlib-retinaface-resnet50",
            "recognizer": "facexlib-arcface-ir-se50",
            "embedding_dimension": 512,
            "device": str(self.device),
            "detector_max_side": self.detector_max_side,
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def detect(self, frame: Any) -> list[DetectedFace]:
        image = np.asarray(frame)
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("face detector expects a three-channel BGR image")
        height, width = image.shape[:2]
        scale = min(1.0, self.detector_max_side / max(height, width))
        detector_image = image
        if scale < 1.0:
            detector_image = cv2.resize(
                image,
                (max(1, round(width * scale)), max(1, round(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        with self._torch.inference_mode():
            raw = self._detector.detect_faces(
                detector_image,
                conf_threshold=self.detection_threshold,
                nms_threshold=0.4,
                use_origin_size=True,
            )
        if raw is None:
            return []
        rows = np.asarray(raw, dtype=np.float32)
        if rows.ndim == 1:
            rows = rows[None, :]
        detections = []
        for row in rows:
            if row.size < 15:
                continue
            detections.append(
                DetectedFace(
                    bbox_xyxy=tuple(float(value) for value in row[:4] / scale),
                    landmarks_xy=(row[5:15].reshape(5, 2) / scale).astype(np.float32),
                    detection_score=float(row[4]),
                )
            )
        return detections

    def embed(self, frame: Any, face: DetectedFace) -> np.ndarray:
        aligned = align_face_112(frame, face.landmarks_xy)
        rgb = np.ascontiguousarray(aligned[:, :, ::-1], dtype=np.float32)
        tensor = self._torch.from_numpy(rgb.transpose(2, 0, 1)).unsqueeze(0)
        tensor = tensor.to(self.device, dtype=self._torch.float32)
        tensor = tensor.div(127.5).sub(1.0)
        with self._torch.inference_mode():
            embedding = self._recognizer(tensor).detach().cpu().numpy()[0]
        return l2_normalize(embedding)


def face_quality_reason(
    frame: Any,
    face: DetectedFace,
    *,
    min_face_size: int,
    min_blur_variance: float,
) -> str | None:
    image = np.asarray(frame)
    height, width = image.shape[:2]
    x1, y1, x2, y2 = face.bbox_xyxy
    if x2 - x1 < min_face_size or y2 - y1 < min_face_size:
        return "face_too_small"
    left, top = max(0, int(np.floor(x1))), max(0, int(np.floor(y1)))
    right, bottom = min(width, int(np.ceil(x2))), min(height, int(np.ceil(y2)))
    if right <= left or bottom <= top:
        return "bbox_outside_frame"
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return "empty_face_crop"
    if min_blur_variance > 0:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < min_blur_variance:
            return "face_too_blurry"
    return None


class FaceGallery:
    """Small local gallery using exact cosine similarity search."""

    def __init__(self, embeddings: Any, person_ids: Iterable[str], names: Iterable[str]) -> None:
        matrix = np.asarray(embeddings, dtype=np.float32)
        ids = tuple(str(value) for value in person_ids)
        display_names = tuple(str(value) for value in names)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
            raise ValueError("gallery embeddings must be a non-empty matrix")
        if matrix.shape[0] != len(ids) or len(ids) != len(display_names):
            raise ValueError("gallery metadata count does not match embeddings")
        if any(not value.strip() for value in ids + display_names):
            raise ValueError("gallery identity fields must not be empty")
        self.embeddings = np.stack([l2_normalize(row) for row in matrix])
        self.person_ids = ids
        self.names = display_names

    @property
    def identity_count(self) -> int:
        return len(set(self.person_ids))

    @property
    def template_count(self) -> int:
        return len(self.person_ids)

    def match(self, embedding: Any, threshold: float) -> MatchResult:
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("cosine threshold must be between -1 and 1")
        query = l2_normalize(embedding)
        if query.shape[0] != self.embeddings.shape[1]:
            raise ValueError("query embedding dimension does not match gallery")
        scores = self.embeddings @ query
        per_identity: dict[str, tuple[float, str]] = {}
        for person_id, name, score in zip(self.person_ids, self.names, scores):
            value = float(score)
            previous = per_identity.get(person_id)
            if previous is None or value > previous[0]:
                per_identity[person_id] = (value, name)
        person_id, (similarity, name) = max(
            per_identity.items(), key=lambda item: item[1][0]
        )
        if similarity < threshold:
            return MatchResult("unknown", None, None, similarity, threshold)
        return MatchResult("recognized", person_id, name, similarity, threshold)

    def save(self, path: Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
        )
        try:
            with os.fdopen(handle, "wb") as stream:
                np.savez_compressed(
                    stream,
                    schema_version=np.asarray([GALLERY_SCHEMA_VERSION]),
                    embeddings=self.embeddings,
                    person_ids=np.asarray(self.person_ids),
                    names=np.asarray(self.names),
                )
            os.replace(temporary_name, destination)
            destination.chmod(0o600)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: Path) -> "FaceGallery":
        with np.load(Path(path), allow_pickle=False) as bundle:
            schema = str(bundle["schema_version"][0])
            if schema != GALLERY_SCHEMA_VERSION:
                raise ValueError(f"unsupported face gallery schema: {schema}")
            return cls(
                bundle["embeddings"],
                bundle["person_ids"].tolist(),
                bundle["names"].tolist(),
            )

    @classmethod
    def enroll_directory(
        cls,
        root: Path,
        backend: FaceBackend,
        *,
        min_face_size: int = 64,
        min_blur_variance: float = 30.0,
    ) -> tuple["FaceGallery", dict[str, Any]]:
        base = Path(root)
        if not base.is_dir():
            raise FileNotFoundError(base)
        identity_dirs = sorted(path for path in base.iterdir() if path.is_dir())
        if not identity_dirs:
            raise ValueError("whitelist directory contains no identity folders")
        embeddings: list[np.ndarray] = []
        person_ids: list[str] = []
        names: list[str] = []
        issues: list[EnrollmentIssue] = []
        accepted_identities: set[str] = set()
        expected_identities: set[str] = set()
        for identity_dir in identity_dirs:
            profile_path = identity_dir / "profile.json"
            profile = (
                json.loads(profile_path.read_text(encoding="utf-8"))
                if profile_path.is_file()
                else {}
            )
            person_id = str(profile.get("person_id", identity_dir.name)).strip()
            name = str(profile.get("name", person_id)).strip()
            if not person_id or not name:
                raise ValueError(f"invalid identity metadata in {profile_path}")
            expected_identities.add(person_id)
            image_paths = sorted(
                path
                for path in identity_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
            if not image_paths:
                issues.append(EnrollmentIssue(person_id, "", "no_images"))
            for image_path in image_paths:
                image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
                if image is None:
                    issues.append(EnrollmentIssue(person_id, image_path.name, "decode_failed"))
                    continue
                faces = backend.detect(image)
                if len(faces) != 1:
                    issues.append(
                        EnrollmentIssue(
                            person_id,
                            image_path.name,
                            "no_face" if not faces else "multiple_faces",
                        )
                    )
                    continue
                reason = face_quality_reason(
                    image,
                    faces[0],
                    min_face_size=min_face_size,
                    min_blur_variance=min_blur_variance,
                )
                if reason is not None:
                    issues.append(EnrollmentIssue(person_id, image_path.name, reason))
                    continue
                embeddings.append(backend.embed(image, faces[0]))
                person_ids.append(person_id)
                names.append(name)
                accepted_identities.add(person_id)
        missing = expected_identities - accepted_identities
        if missing:
            raise ValueError("no usable enrollment image for: " + ", ".join(sorted(missing)))
        gallery = cls(np.stack(embeddings), person_ids, names)
        return gallery, {
            "identity_count": gallery.identity_count,
            "template_count": gallery.template_count,
            "accepted_image_count": len(embeddings),
            "issues": [issue.__dict__ for issue in issues],
        }


def _intersection_fraction(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> float:
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    intersection = max(0.0, min(ix2, ox2) - max(ix1, ox1)) * max(
        0.0, min(iy2, oy2) - max(iy1, oy1)
    )
    area = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    return intersection / area if area > 0 else 0.0


@dataclass(frozen=True)
class FacePersonAssociations:
    person_to_face: dict[int, int]
    ambiguous_person_indices: frozenset[int]


def associate_faces_to_people(
    faces: Iterable[DetectedFace],
    people: Iterable[PersonObservation],
    *,
    upper_body_fraction: float = 0.75,
    min_face_containment: float = 0.75,
    single_person_min_containment: float = 0.5,
    single_person_upper_fraction: float = 0.85,
    ambiguity_margin: float = 0.08,
) -> FacePersonAssociations:
    face_list, person_list = list(faces), list(people)
    if len(face_list) == 1 and len(person_list) == 1:
        face, person = face_list[0], person_list[0]
        fx1, fy1, fx2, fy2 = face.bbox_xyxy
        px1, py1, px2, py2 = person.bbox_xyxy
        center_x, center_y = (fx1 + fx2) / 2.0, (fy1 + fy2) / 2.0
        allowed_bottom = py1 + max(0.0, py2 - py1) * single_person_upper_fraction
        containment = _intersection_fraction(face.bbox_xyxy, person.bbox_xyxy)
        if (
            px1 <= center_x <= px2
            and py1 <= center_y <= allowed_bottom
            and containment >= single_person_min_containment
        ):
            return FacePersonAssociations({0: 0}, frozenset())
        return FacePersonAssociations({}, frozenset())

    candidates: list[tuple[float, int, int]] = []
    ambiguous_people: set[int] = set()
    for face_index, face in enumerate(face_list):
        fx1, fy1, fx2, fy2 = face.bbox_xyxy
        center_x, center_y = (fx1 + fx2) / 2.0, (fy1 + fy2) / 2.0
        face_candidates = []
        for person_index, person in enumerate(person_list):
            px1, py1, px2, py2 = person.bbox_xyxy
            upper_bottom = py1 + max(0.0, py2 - py1) * upper_body_fraction
            containment = _intersection_fraction(face.bbox_xyxy, person.bbox_xyxy)
            if not (px1 <= center_x <= px2 and py1 <= center_y <= upper_bottom):
                continue
            if containment < min_face_containment:
                continue
            offset = abs(center_x - (px1 + px2) / 2.0) / max(1.0, px2 - px1)
            face_candidates.append((containment - 0.2 * offset, person_index, face_index))
        face_candidates.sort(reverse=True)
        if (
            len(face_candidates) > 1
            and face_candidates[0][0] - face_candidates[1][0] < ambiguity_margin
        ):
            ambiguous_people.update((face_candidates[0][1], face_candidates[1][1]))
        elif face_candidates:
            candidates.append(face_candidates[0])
    candidates.sort(reverse=True)
    assigned_people: set[int] = set()
    assigned_faces: set[int] = set()
    result: dict[int, int] = {}
    for _, person_index, face_index in candidates:
        if person_index in assigned_people or face_index in assigned_faces:
            ambiguous_people.add(person_index)
            continue
        assigned_people.add(person_index)
        assigned_faces.add(face_index)
        result[person_index] = face_index
    return FacePersonAssociations(result, frozenset(ambiguous_people))


@dataclass
class TrackIdentity:
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]
    last_seen_ms: int
    state: str = "anonymous"
    person_id: str | None = None
    name: str | None = None
    similarity: float | None = None
    last_face_attempt_ms: int | None = None
    last_face_confirmation_ms: int | None = None
    candidate_person_id: str | None = None
    candidate_name: str | None = None
    candidate_similarity: float | None = None
    candidate_count: int = 0
    candidate_started_ms: int | None = None
    last_face_status: str = "unavailable"
    last_face_similarity: float | None = None
    last_face_bbox_xyxy: tuple[float, float, float, float] | None = None
    last_face_person_bbox_xyxy: tuple[float, float, float, float] | None = None
    last_face_detection_score: float | None = None
    last_face_seen_ms: int | None = None


class TrackIdentityManager:
    def __init__(
        self,
        *,
        confirmation_matches: int = 2,
        confirmation_window_ms: int = 1500,
        lost_timeout_ms: int = 4000,
    ) -> None:
        self.confirmation_matches = int(confirmation_matches)
        self.confirmation_window_ms = int(confirmation_window_ms)
        self.lost_timeout_ms = int(lost_timeout_ms)
        self._tracks: dict[int, TrackIdentity] = {}

    def update_people(
        self, people: Iterable[PersonObservation], timestamp_ms: int
    ) -> list[TrackIdentity]:
        current = list(people)
        for track_id, state in list(self._tracks.items()):
            if timestamp_ms - state.last_seen_ms > self.lost_timeout_ms:
                del self._tracks[track_id]
        for person in current:
            state = self._tracks.get(person.track_id)
            if state is None:
                state = TrackIdentity(person.track_id, person.bbox_xyxy, timestamp_ms)
                self._tracks[person.track_id] = state
            else:
                state.bbox_xyxy = person.bbox_xyxy
                state.last_seen_ms = timestamp_ms
                if state.person_id is not None and state.state == "face_confirmed":
                    state.state = "track_carried"
        return [self._tracks[person.track_id] for person in current]

    def should_recognize(self, track_id: int, timestamp_ms: int, interval_ms: int) -> bool:
        state = self._tracks[track_id]
        return (
            state.candidate_person_id is not None
            or state.last_face_attempt_ms is None
            or timestamp_ms - state.last_face_attempt_ms >= interval_ms
        )

    def record_unavailable(self, track_id: int) -> None:
        state = self._tracks[track_id]
        state.last_face_status = "unavailable"
        if state.person_id is not None:
            state.state = "track_carried"

    def record_match(
        self, track_id: int, match: MatchResult, timestamp_ms: int
    ) -> TrackIdentity:
        state = self._tracks[track_id]
        state.last_face_attempt_ms = timestamp_ms
        state.last_face_status = match.status
        state.last_face_similarity = match.similarity
        if match.status != "recognized" or match.person_id is None:
            self._clear_candidate(state)
            state.state = "track_carried" if state.person_id is not None else "anonymous"
            return state
        if state.person_id == match.person_id:
            state.name = match.name
            state.similarity = match.similarity
            state.last_face_confirmation_ms = timestamp_ms
            state.state = "face_confirmed"
            self._clear_candidate(state)
            return state
        same_candidate = (
            state.candidate_person_id == match.person_id
            and state.candidate_started_ms is not None
            and timestamp_ms - state.candidate_started_ms <= self.confirmation_window_ms
        )
        if same_candidate:
            state.candidate_count += 1
            state.candidate_similarity = max(
                float(state.candidate_similarity or -1.0), match.similarity
            )
        else:
            state.candidate_person_id = match.person_id
            state.candidate_name = match.name
            state.candidate_similarity = match.similarity
            state.candidate_count = 1
            state.candidate_started_ms = timestamp_ms
        if state.candidate_count >= self.confirmation_matches:
            state.person_id = state.candidate_person_id
            state.name = state.candidate_name
            state.similarity = state.candidate_similarity
            state.last_face_confirmation_ms = timestamp_ms
            state.state = "face_confirmed"
            self._clear_candidate(state)
        elif state.person_id is None:
            state.state = "face_candidate"
        else:
            state.state = "track_carried"
        return state

    @staticmethod
    def _clear_candidate(state: TrackIdentity) -> None:
        state.candidate_person_id = None
        state.candidate_name = None
        state.candidate_similarity = None
        state.candidate_count = 0
        state.candidate_started_ms = None


@dataclass(frozen=True)
class FaceRecognitionConfig:
    sample_fps: float = 5.0
    similarity_threshold: float = 0.45
    min_face_size: int = 64
    min_blur_variance: float = 30.0
    reidentify_interval_s: float = 2.0
    identity_lost_timeout_s: float = 4.0
    confirmation_matches: int = 2
    confirmation_window_s: float = 1.5
    max_faces: int = 20

    def __post_init__(self) -> None:
        if self.sample_fps <= 0:
            raise ValueError("face sample fps must be positive")
        if not -1.0 <= self.similarity_threshold <= 1.0:
            raise ValueError("face similarity threshold must be between -1 and 1")
        if self.min_face_size <= 0 or self.min_blur_variance < 0:
            raise ValueError("face quality thresholds are invalid")
        if (
            self.reidentify_interval_s <= 0
            or self.identity_lost_timeout_s <= 0
            or self.confirmation_matches <= 0
            or self.confirmation_window_s <= 0
            or self.max_faces <= 0
        ):
            raise ValueError("face recognition timing values must be positive")


class RealtimeFaceRecognizer:
    """Run face recognition on tracked people supplied by the pose pipeline."""

    def __init__(
        self,
        backend: FaceBackend,
        gallery: FaceGallery,
        config: FaceRecognitionConfig,
    ) -> None:
        self.backend = backend
        self.gallery = gallery
        self.config = config
        self.identities = TrackIdentityManager(
            confirmation_matches=config.confirmation_matches,
            confirmation_window_ms=round(config.confirmation_window_s * 1000),
            lost_timeout_ms=round(config.identity_lost_timeout_s * 1000),
        )
        self.next_sample_at = 0.0

    def process_frame(
        self,
        frame: np.ndarray,
        people: list[PersonObservation],
        *,
        timestamp_ms: int,
        frame_number: int | None,
        primary_track_id: int | None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        tracks = self.identities.update_people(people, timestamp_ms)
        analyze_faces = timestamp_ms >= self.next_sample_at and bool(people)
        detections: list[DetectedFace] = []
        associations = associate_faces_to_people([], people)
        if analyze_faces:
            self.next_sample_at = timestamp_ms + 1000.0 / self.config.sample_fps
            detections = sorted(
                self.backend.detect(frame),
                key=lambda face: face.detection_score,
                reverse=True,
            )[: self.config.max_faces]
            associations = associate_faces_to_people(detections, people)

        observations = []
        recognition_interval_ms = round(self.config.reidentify_interval_s * 1000)
        face_box_cache_ms = max(250, round(2500.0 / self.config.sample_fps))
        for person_index, (person, track) in enumerate(zip(people, tracks)):
            face_index = associations.person_to_face.get(person_index)
            face = detections[face_index] if face_index is not None else None
            quality = "not_analyzed" if not analyze_faces else "face_not_detected"
            source = "person_track"
            if person_index in associations.ambiguous_person_indices:
                quality, source = "face_body_ambiguous", "association_gate"
            elif face is not None:
                track.last_face_bbox_xyxy = face.bbox_xyxy
                track.last_face_person_bbox_xyxy = person.bbox_xyxy
                track.last_face_detection_score = face.detection_score
                track.last_face_seen_ms = timestamp_ms
                quality = face_quality_reason(
                    frame,
                    face,
                    min_face_size=self.config.min_face_size,
                    min_blur_variance=self.config.min_blur_variance,
                )
                due = self.identities.should_recognize(
                    track.track_id, timestamp_ms, recognition_interval_ms
                )
                if quality is None and due:
                    match = self.gallery.match(
                        self.backend.embed(frame, face), self.config.similarity_threshold
                    )
                    track = self.identities.record_match(track.track_id, match, timestamp_ms)
                    source = "arcface"
                elif quality is not None:
                    self.identities.record_unavailable(track.track_id)
                    source = "quality_gate"
                else:
                    source = "track_cache"
            elif analyze_faces and detections:
                quality, source = "face_not_associated", "association_gate"

            status = (
                "recognized"
                if track.person_id is not None
                else "unknown"
                if track.last_face_status == "unknown"
                else "unavailable"
            )
            displayed_face_bbox = face.bbox_xyxy if face is not None else None
            face_bbox_source = "detected" if face is not None else None
            displayed_face_score = face.detection_score if face is not None else None
            if (
                displayed_face_bbox is None
                and track.last_face_bbox_xyxy is not None
                and track.last_face_person_bbox_xyxy is not None
                and track.last_face_seen_ms is not None
                and timestamp_ms - track.last_face_seen_ms <= face_box_cache_ms
            ):
                displayed_face_bbox = remap_bbox(
                    track.last_face_bbox_xyxy,
                    track.last_face_person_bbox_xyxy,
                    person.bbox_xyxy,
                )
                displayed_face_score = track.last_face_detection_score
                face_bbox_source = "track_cache"
            observations.append(
                {
                    "track_id": track.track_id,
                    "primary": track.track_id == primary_track_id,
                    "bbox_xyxy": [round(value, 2) for value in person.bbox_xyxy],
                    "face_bbox_xyxy": (
                        [round(value, 2) for value in displayed_face_bbox]
                        if displayed_face_bbox is not None
                        else None
                    ),
                    "face_bbox_source": face_bbox_source,
                    "face_detection_score": (
                        round(displayed_face_score, 6)
                        if displayed_face_score is not None
                        else None
                    ),
                    "face_quality": "passed" if quality is None else quality,
                    "recognition_source": source,
                    "identity_state": track.state,
                    "identity_confidence": (
                        "high"
                        if track.state == "face_confirmed"
                        else "medium"
                        if track.state == "track_carried" and track.person_id is not None
                        else "none"
                    ),
                    "status": status,
                    "person_id": track.person_id if status == "recognized" else None,
                    "name": track.name if status == "recognized" else None,
                    "similarity": (
                        round(float(track.similarity), 6)
                        if status == "recognized" and track.similarity is not None
                        else round(float(track.last_face_similarity), 6)
                        if status == "unknown" and track.last_face_similarity is not None
                        else None
                    ),
                }
            )
        primary = next((item for item in observations if item["primary"]), None)
        return {
            "state": "ready",
            "frame_number": frame_number,
            "sampled_this_frame": analyze_faces,
            "raw_face_detections": len(detections),
            "people": observations,
            "primary": primary,
            "inference_ms": round((time.perf_counter() - started) * 1000, 2),
            "backend": self.backend.metadata,
            "gallery": {
                "identity_count": self.gallery.identity_count,
                "template_count": self.gallery.template_count,
            },
        }


def people_from_pose_result(result: Any) -> list[PersonObservation]:
    if result.boxes is None or len(result.boxes) == 0 or result.boxes.id is None:
        return []
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    confidences = result.boxes.conf.detach().cpu().numpy()
    track_ids = result.boxes.id.detach().cpu().numpy()
    return [
        PersonObservation(
            track_id=int(track_id),
            bbox_xyxy=tuple(float(value) for value in box),
            confidence=float(confidence),
        )
        for box, confidence, track_id in zip(boxes, confidences, track_ids)
    ]


def remap_bbox(
    bbox: tuple[float, float, float, float],
    source_person_bbox: tuple[float, float, float, float],
    target_person_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Map a cached face box with the movement and scale of its person box."""

    sx1, sy1, sx2, sy2 = source_person_bbox
    tx1, ty1, tx2, ty2 = target_person_bbox
    source_width = max(1.0, sx2 - sx1)
    source_height = max(1.0, sy2 - sy1)
    target_width = max(1.0, tx2 - tx1)
    target_height = max(1.0, ty2 - ty1)
    x1, y1, x2, y2 = bbox
    return (
        tx1 + (x1 - sx1) / source_width * target_width,
        ty1 + (y1 - sy1) / source_height * target_height,
        tx1 + (x2 - sx1) / source_width * target_width,
        ty1 + (y2 - sy1) / source_height * target_height,
    )


def draw_identity_annotations(frame: np.ndarray, identity: dict[str, Any]) -> np.ndarray:
    output = frame.copy()
    for person in identity.get("people") or []:
        status = person.get("status")
        color = (
            (40, 190, 40)
            if status == "recognized"
            else (0, 165, 255)
            if status == "unknown"
            else (120, 120, 120)
        )
        face_bbox = person.get("face_bbox_xyxy")
        if face_bbox is not None:
            fx1, fy1, fx2, fy2 = (round(float(value)) for value in face_bbox)
            cv2.rectangle(output, (fx1, fy1), (fx2, fy2), color, 2, cv2.LINE_AA)
            label_x, label_y = fx1, fy1
        else:
            x1, y1, _, _ = (round(float(value)) for value in person["bbox_xyxy"])
            label_x, label_y = x1, y1
        if status == "recognized":
            label_identity = str(person.get("name") or person.get("person_id"))
            if not label_identity.isascii():
                label_identity = str(person.get("person_id") or "recognized")
            label = f"ID {label_identity} sim={float(person['similarity']):.3f}"
        elif status == "unknown":
            similarity = person.get("similarity")
            label = "ID unknown" + (f" sim={float(similarity):.3f}" if similarity is not None else "")
        else:
            label = "ID unavailable"
        baseline_y = max(20, label_y - 8)
        (text_width, text_height), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
        )
        cv2.rectangle(
            output,
            (max(0, label_x), max(0, baseline_y - text_height - 7)),
            (max(0, label_x) + text_width + 8, baseline_y + 3),
            color,
            -1,
        )
        cv2.putText(
            output,
            label,
            (max(0, label_x) + 4, baseline_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    return output
