"""Bit-exact M1 generated stimuli and immutable canonical PCM buffers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import math
import sys
from types import MappingProxyType
from typing import Any, TypeAlias

import numpy as np

from .contracts import LoadedContract, validate_document


FrozenJson: TypeAlias = (
    str | int | float | bool | None | tuple["FrozenJson", ...] | Mapping[str, "FrozenJson"]
)


class StimulusGenerationError(ValueError):
    """A manifest is schema-valid but violates generator semantics."""


def _freeze(value: Any) -> FrozenJson:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported metadata value {type(value).__name__}")


def _thaw(value: FrozenJson) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


@dataclass(frozen=True)
class GeneratorIdentity:
    id: str
    version: str


@dataclass(frozen=True)
class AudioFormat:
    sample_rate_hz: int
    frame_count: int
    channel_count: int
    sample_format: str = "float32"
    layout: str = "frames_channels_interleaved"
    endianness: str = "little"
    full_scale_min: float = -1.0
    full_scale_max: float = 1.0


@dataclass(frozen=True)
class Channel:
    index: int
    id: str


@dataclass(frozen=True)
class StimulusMetadata:
    generator: GeneratorIdentity
    parameters: Mapping[str, FrozenJson]
    seed: int
    audio_format: AudioFormat
    channel_map: tuple[Channel, ...]
    manifest_sha256: str
    pcm_sha256: str
    schema_version: str = "1.0.0"

    def to_document(self) -> dict[str, Any]:
        """Return a detached JSON representation suitable for strict serialization."""
        return {
            "schema_version": self.schema_version,
            "generator": {
                "id": self.generator.id,
                "version": self.generator.version,
            },
            "parameters": _thaw(self.parameters),
            "seed": self.seed,
            "audio_format": {
                "sample_rate_hz": self.audio_format.sample_rate_hz,
                "frame_count": self.audio_format.frame_count,
                "channel_count": self.audio_format.channel_count,
                "sample_format": self.audio_format.sample_format,
                "layout": self.audio_format.layout,
                "endianness": self.audio_format.endianness,
                "full_scale_min": self.audio_format.full_scale_min,
                "full_scale_max": self.audio_format.full_scale_max,
            },
            "channel_map": [
                {"index": channel.index, "id": channel.id}
                for channel in self.channel_map
            ],
            "manifest_sha256": self.manifest_sha256,
            "pcm_sha256": self.pcm_sha256,
        }


@dataclass(frozen=True)
class GeneratedStimulus:
    """Immutable reference PCM; candidate processing requires ``candidate_copy``."""

    pcm: np.ndarray
    metadata: StimulusMetadata

    def candidate_copy(self) -> np.ndarray:
        """Return an explicit writable C-contiguous candidate buffer."""
        return np.array(self.pcm, dtype=np.float32, order="C", copy=True)


def canonical_pcm_bytes(pcm: np.ndarray) -> bytes:
    """Serialize canonical PCM as headerless little-endian binary32 in C-order."""
    if pcm.ndim != 2:
        raise StimulusGenerationError("canonical PCM must have rank 2")
    if not pcm.flags.c_contiguous:
        raise StimulusGenerationError("canonical PCM must be C-contiguous")
    if pcm.dtype != np.dtype(np.float32):
        raise StimulusGenerationError("canonical PCM must have dtype float32")
    if not np.isfinite(pcm).all():
        raise StimulusGenerationError("canonical PCM contains a non-finite sample")
    if np.any(pcm < np.float32(-1.0)) or np.any(pcm > np.float32(1.0)):
        raise StimulusGenerationError("canonical PCM exceeds inclusive full scale [-1, 1]")
    return pcm.astype("<f4", copy=False).tobytes(order="C")


def _parameters(stimulus: Mapping[str, Any], expected: set[str]) -> Mapping[str, Any]:
    parameters = stimulus["parameters"]
    actual = set(parameters)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise StimulusGenerationError(
            f"generator parameters mismatch: missing={missing}, unknown={unknown}"
        )
    return parameters


def _binary32(value: Any, name: str, *, strictly_positive: bool = False) -> np.float32:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StimulusGenerationError(f"{name} must be a JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise StimulusGenerationError(f"{name} must be finite")
    if numeric < -1.0 or numeric > 1.0:
        raise StimulusGenerationError(f"{name} exceeds inclusive full scale [-1, 1]")
    if strictly_positive and numeric <= 0.0:
        raise StimulusGenerationError(f"{name} must be greater than zero")
    return np.float32(numeric)


def _validate_channels(channel_items: list[dict[str, Any]]) -> tuple[Channel, ...]:
    indices = [item["index"] for item in channel_items]
    identifiers = [item["id"] for item in channel_items]
    if indices != list(range(len(channel_items))):
        raise StimulusGenerationError(
            "channel_map indices must be unique, ordered, and contiguous from zero"
        )
    if len(set(identifiers)) != len(identifiers):
        raise StimulusGenerationError("channel_map IDs must be unique")
    return tuple(Channel(index=item["index"], id=item["id"]) for item in channel_items)


def _constant(
    stimulus: Mapping[str, Any], frames: int, channels: int
) -> np.ndarray:
    if stimulus["seed"] != 0:
        raise StimulusGenerationError("constant/1 requires seed=0")
    parameters = _parameters(stimulus, {"value"})
    value = _binary32(parameters["value"], "value")
    return np.full((frames, channels), value, dtype=np.float32, order="C")


def _impulse(stimulus: Mapping[str, Any], frames: int, channels: int) -> np.ndarray:
    if stimulus["seed"] != 0:
        raise StimulusGenerationError("impulse/1 requires seed=0")
    parameters = _parameters(
        stimulus, {"amplitude", "frame_index", "channel_indices"}
    )
    amplitude = _binary32(parameters["amplitude"], "amplitude")
    frame_index = parameters["frame_index"]
    channel_indices = parameters["channel_indices"]
    if isinstance(frame_index, bool) or not isinstance(frame_index, int):
        raise StimulusGenerationError("frame_index must be an integer")
    if not 0 <= frame_index < frames:
        raise StimulusGenerationError("frame_index is outside the generated buffer")
    if (
        not isinstance(channel_indices, list)
        or not channel_indices
        or any(isinstance(index, bool) or not isinstance(index, int) for index in channel_indices)
        or len(set(channel_indices)) != len(channel_indices)
        or any(index < 0 or index >= channels for index in channel_indices)
    ):
        raise StimulusGenerationError(
            "channel_indices must be unique in-range integer channel indices"
        )
    pcm = np.zeros((frames, channels), dtype=np.float32, order="C")
    pcm[frame_index, channel_indices] = amplitude
    return pcm


def _channel_identification(
    stimulus: Mapping[str, Any], frames: int, channels: int
) -> np.ndarray:
    if stimulus["seed"] != 0:
        raise StimulusGenerationError("channel-identification/1 requires seed=0")
    parameters = _parameters(
        stimulus, {"amplitude", "start_frame", "spacing_frames"}
    )
    amplitude = _binary32(parameters["amplitude"], "amplitude")
    start = parameters["start_frame"]
    spacing = parameters["spacing_frames"]
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise StimulusGenerationError("start_frame must be a non-negative integer")
    if isinstance(spacing, bool) or not isinstance(spacing, int) or spacing < 1:
        raise StimulusGenerationError("spacing_frames must be a positive integer")
    if start + (channels - 1) * spacing >= frames:
        raise StimulusGenerationError("channel-identification impulses do not fit")
    pcm = np.zeros((frames, channels), dtype=np.float32, order="C")
    for channel in range(channels):
        pcm[start + channel * spacing, channel] = amplitude
    return pcm


def _prbs15(stimulus: Mapping[str, Any], frames: int, channels: int) -> np.ndarray:
    parameters = _parameters(stimulus, {"amplitude"})
    seed = stimulus["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 1 <= seed <= 32767:
        raise StimulusGenerationError("prbs15/1 seed/state must be in [1, 32767]")
    amplitude = _binary32(parameters["amplitude"], "amplitude", strictly_positive=True)
    pcm = np.empty((frames, channels), dtype=np.float32, order="C")
    for channel in range(channels):
        state = 1 + ((seed - 1 + channel) % 32767)
        for frame in range(frames):
            pcm[frame, channel] = amplitude if state & 1 else -amplitude
            feedback = ((state >> 0) ^ (state >> 1)) & 1
            state = ((state >> 1) | (feedback << 14)) & 0x7FFF
            if state == 0:
                raise StimulusGenerationError("prbs15 entered the prohibited zero state")
    return pcm


_GENERATORS = {
    ("constant", "1"): _constant,
    ("impulse", "1"): _impulse,
    ("channel-identification", "1"): _channel_identification,
    ("prbs15", "1"): _prbs15,
}


def generate_stimulus(manifest: LoadedContract) -> GeneratedStimulus:
    """Generate one immutable, digest-identified stimulus from a manifest."""
    if sys.byteorder != "little":
        raise StimulusGenerationError("M1 canonical NumPy buffers require little-endian host")
    validate_document(manifest.document, contract="manifest")
    document = manifest.document
    stimulus = document["stimulus"]
    generator_document = stimulus["generator"]
    identity = (generator_document["id"], generator_document["version"])
    try:
        generator = _GENERATORS[identity]
    except KeyError as error:
        raise StimulusGenerationError(
            f"unknown generator/version {identity[0]!r}/{identity[1]!r}"
        ) from error

    audio = document["audio_format"]
    channel_map = _validate_channels(document["channel_map"])
    frame_count = audio["frame_count"]
    pcm = generator(stimulus, frame_count, len(channel_map))
    canonical = canonical_pcm_bytes(pcm)
    immutable_pcm = np.frombuffer(canonical, dtype="<f4").reshape(
        (frame_count, len(channel_map)), order="C"
    )
    pcm_sha256 = hashlib.sha256(canonical).hexdigest()
    metadata = StimulusMetadata(
        generator=GeneratorIdentity(id=identity[0], version=identity[1]),
        parameters=_freeze(stimulus["parameters"]),
        seed=stimulus["seed"],
        audio_format=AudioFormat(
            sample_rate_hz=audio["sample_rate_hz"],
            frame_count=frame_count,
            channel_count=len(channel_map),
        ),
        channel_map=channel_map,
        manifest_sha256=manifest.sha256,
        pcm_sha256=pcm_sha256,
    )
    validate_document(metadata.to_document(), contract="stimulus_metadata")
    return GeneratedStimulus(pcm=immutable_pcm, metadata=metadata)


__all__ = [
    "AudioFormat",
    "Channel",
    "GeneratedStimulus",
    "GeneratorIdentity",
    "StimulusGenerationError",
    "StimulusMetadata",
    "canonical_pcm_bytes",
    "generate_stimulus",
]
