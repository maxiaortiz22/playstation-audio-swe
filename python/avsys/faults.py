"""Deterministic, labeled fault injection for canonical M1 PCM buffers.

All intervals are zero-based and half-open.  Every injector returns a detached,
writable C-contiguous ``float32`` candidate and leaves its input untouched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

import numpy as np


class FaultParameterError(ValueError):
    """A PCM buffer or declared fault parameter violates the fault contract."""


@dataclass(frozen=True)
class FaultRecord:
    """Immutable reproduction record for one injected fault."""

    type: str
    label: str
    parameters: Mapping[str, Any]
    units: Mapping[str, str]


@dataclass(frozen=True)
class FaultInjection:
    """A detached candidate paired with its immutable reproduction record."""

    candidate: np.ndarray
    record: FaultRecord


def _canonical_pcm(pcm: np.ndarray) -> None:
    if not isinstance(pcm, np.ndarray):
        raise FaultParameterError("pcm must be a NumPy array")
    if pcm.dtype != np.dtype(np.float32):
        raise FaultParameterError("pcm must have dtype float32")
    if pcm.ndim != 2:
        raise FaultParameterError("pcm must have rank 2 shaped (frames, channels)")
    if not pcm.flags.c_contiguous:
        raise FaultParameterError("pcm must be C-contiguous in frames/channels layout")
    if pcm.shape[0] == 0 or pcm.shape[1] == 0:
        raise FaultParameterError("pcm must contain at least one frame and one channel")
    if not np.isfinite(pcm).all():
        raise FaultParameterError("pcm must contain only finite samples")


def _label(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FaultParameterError("label must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FaultParameterError(f"{name} must be an integer")
    return value


def _record(
    fault_type: str,
    label: str,
    parameters: dict[str, Any],
    units: dict[str, str],
) -> FaultRecord:
    return FaultRecord(
        type=fault_type,
        label=_label(label),
        parameters=MappingProxyType(parameters),
        units=MappingProxyType(units),
    )


def inject_integer_delay(
    pcm: np.ndarray, *, delay_frames: int, label: str
) -> FaultInjection:
    """Shift PCM without changing length.

    Positive delay means the candidate occurs later: ``delay_frames`` leading
    frames are positive zero and the same number of trailing source frames are
    discarded.  Negative delay advances the candidate, discarding leading
    source frames and adding positive-zero trailing frames.  At least one
    source/candidate pair must remain, so ``abs(delay_frames) < frame_count``.
    """

    _canonical_pcm(pcm)
    delay = _integer(delay_frames, "delay_frames")
    frames = pcm.shape[0]
    if abs(delay) >= frames:
        raise FaultParameterError(
            "abs(delay_frames) must be smaller than the PCM frame count"
        )

    if delay == 0:
        candidate = np.array(pcm, dtype=np.float32, order="C", copy=True)
    else:
        candidate = np.zeros(pcm.shape, dtype=np.float32, order="C")
        if delay > 0:
            candidate[delay:, :] = pcm[:-delay, :]
        else:
            advance = -delay
            candidate[:-advance, :] = pcm[advance:, :]

    return FaultInjection(
        candidate=candidate,
        record=_record(
            "integer_delay",
            label,
            {"delay_frames": delay},
            {"delay_frames": "frames"},
        ),
    )


def inject_stereo_channel_swap(pcm: np.ndarray, *, label: str) -> FaultInjection:
    """Exchange columns 0 and 1 of an exactly stereo buffer."""

    _canonical_pcm(pcm)
    if pcm.shape[1] != 2:
        raise FaultParameterError("stereo channel swap requires exactly two channels")
    candidate = np.array(pcm[:, ::-1], dtype=np.float32, order="C", copy=True)
    return FaultInjection(
        candidate=candidate,
        record=_record(
            "stereo_channel_swap",
            label,
            {"observed_to_source_channel_indices": (1, 0)},
            {"observed_to_source_channel_indices": "channel_index"},
        ),
    )


def inject_dropout(
    pcm: np.ndarray,
    *,
    start_frame: int,
    end_frame: int,
    channel_indices: Sequence[int],
    fill_value_linear_fs: float,
    label: str,
) -> FaultInjection:
    """Replace ``[start_frame, end_frame)`` on the declared channels.

    ``fill_value_linear_fs=0.0`` injects an exact-zero dropout.  A finite,
    non-zero value can inject a deterministic near-silence dropout.  The fill
    must lie in the inclusive nominal full-scale interval ``[-1, 1]``.
    """

    _canonical_pcm(pcm)
    start = _integer(start_frame, "start_frame")
    end = _integer(end_frame, "end_frame")
    if not 0 <= start < end <= pcm.shape[0]:
        raise FaultParameterError(
            "dropout interval must satisfy 0 <= start_frame < end_frame <= frame_count"
        )
    if isinstance(channel_indices, (str, bytes)) or not isinstance(
        channel_indices, Sequence
    ):
        raise FaultParameterError("channel_indices must be a sequence of integers")
    channels = tuple(_integer(value, "channel index") for value in channel_indices)
    if not channels:
        raise FaultParameterError("channel_indices must not be empty")
    if len(set(channels)) != len(channels):
        raise FaultParameterError("channel_indices must be unique")
    if any(channel < 0 or channel >= pcm.shape[1] for channel in channels):
        raise FaultParameterError("channel_indices contains an out-of-range channel")
    if isinstance(fill_value_linear_fs, bool) or not isinstance(
        fill_value_linear_fs, (int, float)
    ):
        raise FaultParameterError("fill_value_linear_fs must be a number")
    fill = float(fill_value_linear_fs)
    if not math.isfinite(fill) or not -1.0 <= fill <= 1.0:
        raise FaultParameterError(
            "fill_value_linear_fs must be finite and inside inclusive full scale [-1, 1]"
        )

    candidate = np.array(pcm, dtype=np.float32, order="C", copy=True)
    candidate[start:end, channels] = np.float32(fill)
    return FaultInjection(
        candidate=candidate,
        record=_record(
            "dropout",
            label,
            {
                "start_frame": start,
                "end_frame": end,
                "channel_indices": channels,
                "fill_value_linear_fs": float(np.float32(fill)),
            },
            {
                "start_frame": "frames",
                "end_frame": "frames_exclusive",
                "channel_indices": "channel_index",
                "fill_value_linear_fs": "linear_FS",
            },
        ),
    )


__all__ = [
    "FaultInjection",
    "FaultParameterError",
    "FaultRecord",
    "inject_dropout",
    "inject_integer_delay",
    "inject_stereo_channel_swap",
]
