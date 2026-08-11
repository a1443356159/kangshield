from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Protocol

from .contracts import ModelBinding, SpeechSegment
from .privacy import sha256_file
from .streaming import AudioBuffer


__all__ = [
    "SpeechSegment",
    "SpeechBackend",
    "FunASRSpeechBackend",
    "WhisperSpeechBackend",
]


class SpeechBackend(Protocol):
    @property
    def bindings(self) -> list[ModelBinding]: ...

    def transcribe(self, audio: AudioBuffer) -> list[SpeechSegment]: ...


SEMANTIC_KEYWORDS = {
    "help_request": ("救命", "帮帮我", "帮我一下", "快来人"),
    "fall_related": ("摔倒", "跌倒", "摔了", "起不来"),
    "fraud_related": (
        "验证码",
        "转账",
        "银行卡",
        "密码",
        "安全账户",
        "公安局",
    ),
}

MODEL_REPOSITORIES = {
    "paraformer-zh": "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "fsmn-vad": "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    "ct-punc": "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
}
MODEL_LICENSES = {
    repository: "Apache-2.0"
    for repository in MODEL_REPOSITORIES.values()
}
MODEL_CACHE_ALIASES = {
    alias: repository.replace("/", "--", 1)
    for alias, repository in MODEL_REPOSITORIES.items()
}

WHISPER_SMALL_VERSION = "20250625"
WHISPER_SMALL_SHA256 = (
    "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794"
)
WHISPER_SMALL_URL = (
    "https://openaipublic.azureedge.net/main/whisper/models/"
    f"{WHISPER_SMALL_SHA256}/small.pt"
)


def tag_transcript(text: str) -> list[str]:
    return sorted(
        category
        for category, keywords in SEMANTIC_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    )


class FunASRSpeechBackend:
    """Mandarin VAD + ASR + punctuation adapter backed by FunASR."""

    def __init__(
        self,
        model: str = "paraformer-zh",
        vad_model: str = "fsmn-vad",
        punc_model: str = "ct-punc",
        device: str = "auto",
        language: str = "zh",
        max_single_segment_ms: int = 30000,
        offline: bool = False,
    ) -> None:
        if max_single_segment_ms <= 0:
            raise ValueError("max_single_segment_ms must be positive")
        try:
            import funasr
            import torch
            from funasr import AutoModel
        except ImportError as error:
            raise RuntimeError(
                f"FunASR backend dependency import failed: {error}"
            ) from error

        if device == "auto":
            resolved_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            resolved_device = device
        self.language = language
        self.device = resolved_device
        self.model_name = model
        self.vad_model_name = vad_model
        self.punc_model_name = punc_model
        resolved_model = _resolve_model_reference(model, offline=offline)
        resolved_vad_model = _resolve_model_reference(vad_model, offline=offline)
        resolved_punc_model = _resolve_model_reference(punc_model, offline=offline)
        self._model = AutoModel(
            model=resolved_model,
            vad_model=resolved_vad_model,
            vad_kwargs={"max_single_segment_time": max_single_segment_ms},
            punc_model=resolved_punc_model,
            device=resolved_device,
            disable_update=True,
        )
        version = getattr(funasr, "__version__", "unknown")
        shared_configuration = {
            "sample_rate_hz": 16000,
            "language": language,
            "max_single_segment_ms": max_single_segment_ms,
            "offline": offline,
            "funasr_version": version,
        }
        self._bindings = [
            ModelBinding(
                task="voice_activity_detection",
                backend="funasr",
                model_name=MODEL_REPOSITORIES.get(vad_model, vad_model),
                model_version=_snapshot_version(resolved_vad_model),
                model_digest=_weight_digest(resolved_vad_model),
                license=_model_license(vad_model),
                device=resolved_device,
                configuration=shared_configuration,
            ),
            ModelBinding(
                task="mandarin_speech_recognition",
                backend="funasr",
                model_name=MODEL_REPOSITORIES.get(model, model),
                model_version=_snapshot_version(resolved_model),
                model_digest=_weight_digest(resolved_model),
                license=_model_license(model),
                device=resolved_device,
                configuration=shared_configuration,
            ),
            ModelBinding(
                task="text_punctuation",
                backend="funasr",
                model_name=MODEL_REPOSITORIES.get(punc_model, punc_model),
                model_version=_snapshot_version(resolved_punc_model),
                model_digest=_weight_digest(resolved_punc_model),
                license=_model_license(punc_model),
                device=resolved_device,
                configuration={
                    "language": language,
                    "offline": offline,
                    "funasr_version": version,
                },
            ),
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return list(self._bindings)

    def transcribe(self, audio: AudioBuffer) -> list[SpeechSegment]:
        raw_result = self._model.generate(
            input=audio.samples,
            fs=audio.sample_rate_hz,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
        return _normalize_funasr_result(
            raw_result,
            duration_ms=audio.duration_ms,
            language=self.language,
        )


class WhisperSpeechBackend:
    """Pinned OpenAI Whisper small adapter for the V1-M3 Mandarin comparison."""

    def __init__(
        self,
        model_path: Path | str = Path("models/whisper/small.pt"),
        device: str = "auto",
        language: str = "zh",
        task: str = "transcribe",
        beam_size: int = 5,
        temperature: float = 0.0,
        fp16: bool | None = None,
        condition_on_previous_text: bool = False,
        no_speech_threshold: float = 0.6,
        logprob_threshold: float = -1.0,
        compression_ratio_threshold: float = 2.4,
    ) -> None:
        if beam_size <= 0:
            raise ValueError("beam_size must be positive")
        if task != "transcribe":
            raise ValueError("V1-M3 Whisper task must remain transcribe")
        path = Path(model_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Whisper checkpoint not found: {path}")
        digest = sha256_file(path)
        if digest != WHISPER_SMALL_SHA256:
            raise ValueError(
                "Whisper small checkpoint digest changed; review the upstream "
                "revision before updating the V1-M3 candidate"
            )
        try:
            import torch
            import whisper
        except ImportError as error:
            raise RuntimeError(
                f"OpenAI Whisper backend dependency import failed: {error}"
            ) from error

        resolved_device = (
            "cuda:0" if device == "auto" and torch.cuda.is_available() else device
        )
        if resolved_device == "auto":
            resolved_device = "cpu"
        resolved_fp16 = (
            resolved_device.startswith("cuda") if fp16 is None else fp16
        )
        self.language = language
        self.task = task
        self.device = resolved_device
        self.beam_size = beam_size
        self.temperature = float(temperature)
        self.fp16 = resolved_fp16
        self.condition_on_previous_text = condition_on_previous_text
        self.no_speech_threshold = no_speech_threshold
        self.logprob_threshold = logprob_threshold
        self.compression_ratio_threshold = compression_ratio_threshold
        self._model = whisper.load_model(str(path), device=resolved_device)
        self._bindings = [
            ModelBinding(
                task="mandarin_speech_recognition",
                backend="openai-whisper",
                model_name="small",
                model_version=WHISPER_SMALL_VERSION,
                model_digest=digest,
                license="MIT",
                device=resolved_device,
                configuration={
                    "checkpoint_path": str(path),
                    "official_checkpoint_url": WHISPER_SMALL_URL,
                    "parameter_count": "244M",
                    "language": language,
                    "task": task,
                    "beam_size": beam_size,
                    "temperature": self.temperature,
                    "fp16": resolved_fp16,
                    "condition_on_previous_text": condition_on_previous_text,
                    "no_speech_threshold": no_speech_threshold,
                    "logprob_threshold": logprob_threshold,
                    "compression_ratio_threshold": compression_ratio_threshold,
                    "verbose": None,
                    "openai_whisper_version": getattr(
                        whisper, "__version__", "unknown"
                    ),
                    "segment_confidence": "not_reported_uncalibrated",
                },
            )
        ]

    @property
    def bindings(self) -> list[ModelBinding]:
        return list(self._bindings)

    def transcribe(self, audio: AudioBuffer) -> list[SpeechSegment]:
        if audio.sample_rate_hz != 16000:
            raise ValueError("Whisper comparison input must be 16 kHz")
        raw_result = self._model.transcribe(
            audio.samples,
            language=self.language,
            task=self.task,
            beam_size=self.beam_size,
            temperature=self.temperature,
            fp16=self.fp16,
            condition_on_previous_text=self.condition_on_previous_text,
            no_speech_threshold=self.no_speech_threshold,
            logprob_threshold=self.logprob_threshold,
            compression_ratio_threshold=self.compression_ratio_threshold,
            word_timestamps=False,
            verbose=None,
        )
        return _normalize_whisper_result(
            raw_result,
            duration_ms=audio.duration_ms,
            language=self.language,
        )


def _normalize_funasr_result(
    raw_result: object,
    duration_ms: int,
    language: str,
) -> list[SpeechSegment]:
    if isinstance(raw_result, dict):
        results = [raw_result]
    elif isinstance(raw_result, list):
        results = [item for item in raw_result if isinstance(item, dict)]
    else:
        raise ValueError("FunASR returned an unsupported result shape")

    segments: list[SpeechSegment] = []
    for item in results:
        sentence_info = item.get("sentence_info")
        if isinstance(sentence_info, list) and sentence_info:
            for sentence in sentence_info:
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text") or "").strip()
                start_ms = _bounded_ms(sentence.get("start"), 0, duration_ms)
                end_ms = _bounded_ms(sentence.get("end"), duration_ms, duration_ms)
                if end_ms < start_ms:
                    end_ms = start_ms
                if text or end_ms > start_ms:
                    segments.append(
                        SpeechSegment(
                            start_ms=start_ms,
                            end_ms=end_ms,
                            text=text,
                            language=language,
                        )
                    )
            continue

        text = str(item.get("text") or "").strip()
        timestamp = item.get("timestamp")
        timestamp_pairs = (
            [pair for pair in timestamp if isinstance(pair, (list, tuple)) and len(pair) >= 2]
            if isinstance(timestamp, list)
            else []
        )
        if timestamp_pairs:
            start_ms = _bounded_ms(timestamp_pairs[0][0], 0, duration_ms)
            end_ms = _bounded_ms(timestamp_pairs[-1][1], duration_ms, duration_ms)
        else:
            start_ms = 0
            end_ms = duration_ms
        if text or timestamp_pairs:
            segments.append(
                SpeechSegment(
                    start_ms=start_ms,
                    end_ms=max(start_ms, end_ms),
                    text=text,
                    language=language,
                )
            )
    return segments


def _normalize_whisper_result(
    raw_result: object,
    duration_ms: int,
    language: str,
) -> list[SpeechSegment]:
    if not isinstance(raw_result, dict):
        raise ValueError("Whisper returned an unsupported result shape")
    raw_segments = raw_result.get("segments")
    segments: list[SpeechSegment] = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            start_ms = _bounded_seconds_ms(item.get("start"), 0, duration_ms)
            end_ms = _bounded_seconds_ms(
                item.get("end"), duration_ms, duration_ms
            )
            end_ms = max(start_ms, end_ms)
            if text or end_ms > start_ms:
                segments.append(
                    SpeechSegment(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                        language=language,
                    )
                )
    if segments:
        return segments
    text = str(raw_result.get("text") or "").strip()
    if not text:
        return []
    return [
        SpeechSegment(
            start_ms=0,
            end_ms=duration_ms,
            text=text,
            language=language,
        )
    ]


def _bounded_seconds_ms(value: object, default: int, duration_ms: int) -> int:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return max(0, min(round(float(value) * 1000.0), duration_ms))
    return max(0, min(default, duration_ms))


def _bounded_ms(value: object, default: int, duration_ms: int) -> int:
    if isinstance(value, (int, float)):
        return max(0, min(round(value), duration_ms))
    return max(0, min(default, duration_ms))


def _model_license(reference: str) -> str:
    repository = MODEL_REPOSITORIES.get(reference, reference)
    return MODEL_LICENSES.get(repository, "model-license-review-required")


def _resolve_model_reference(reference: str, *, offline: bool) -> str:
    supplied_path = Path(reference).expanduser()
    if supplied_path.is_dir() and (supplied_path / "config.yaml").is_file():
        return str(supplied_path)

    cache_name = MODEL_CACHE_ALIASES.get(reference)
    if cache_name:
        for root in _model_cache_roots():
            for candidate in (
                root / cache_name / "snapshots" / "master",
                root / cache_name,
            ):
                if (candidate / "config.yaml").is_file():
                    return str(candidate)
    if offline:
        raise FileNotFoundError(
            f"offline model snapshot not found for {reference!r}; prefetch it on the login node"
        )
    return reference


def _model_cache_roots() -> list[Path]:
    roots: list[Path] = []
    configured = os.environ.get("MODELSCOPE_CACHE")
    if configured:
        configured_path = Path(configured).expanduser()
        roots.extend([configured_path, configured_path / "models"])
    roots.extend(
        [
            Path.home() / ".cache" / "modelscope" / "models",
            Path.home() / ".cache" / "modelscope" / "hub" / "models",
        ]
    )
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _snapshot_version(reference: str) -> str | None:
    path = Path(reference)
    if path.is_dir() and path.parent.name == "snapshots":
        return path.name
    return None


def _weight_digest(reference: str) -> str | None:
    path = Path(reference)
    weight = path / "model.pt" if path.is_dir() else path
    return sha256_file(weight) if weight.is_file() else None
