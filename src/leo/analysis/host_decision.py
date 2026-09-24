"""Numerical port for six-window adaptive evidence from one native-10M dwell.

The caller owns source identity, queuing, feedback and release provenance. This
component owns filtering, support bounds, screening and blind confirmation.
"""

from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.templates import qin_edge_pilot_frame


class _Result(ct.Structure):
    _fields_ = [
        *[
            (name, ct.c_uint32)
            for name in (
                "version",
                "outcome",
                "screen_mask",
                "confirmation_mask",
                "supported_start",
                "supported_end",
                "candidate_supported",
                "reserved",
            )
        ],
        ("epoch", ct.c_int32),
        ("fractional_complete", ct.c_int32),
        *[
            (name, ct.c_double)
            for name in (
                "fractional_offset",
                "cfo_hz",
                "exact_score",
                "margin",
                "filter_cpu_ms",
                "cpu_ms",
                "wall_ms",
            )
        ],
        ("screen_scores", ct.c_double * 6),
    ]


@dataclass(frozen=True, slots=True)
class HostDecisionEvidence:
    outcome: Literal["unknown", "detected", "not_detected"]
    screen_mask: int
    confirmation_mask: int
    supported_start: int
    supported_end: int
    candidate_supported: bool
    epoch: int
    fractional_complete: bool
    fractional_offset: float
    cfo_hz: float
    exact_score: float
    margin: float
    filter_cpu_ms: float
    cpu_ms: float
    wall_ms: float
    screen_scores: tuple[float, ...]

    @property
    def source_epoch_offset(self) -> float | None:
        """Native sample coordinate relative to valid dwell start, delay corrected."""
        if not self.candidate_supported or not self.fractional_complete:
            return None
        window = self.confirmation_mask.bit_length() - 1
        return 4 * (window * 50000 + self.epoch + self.fractional_offset) - 80


class NativeHostDecision:
    """One non-reentrant, bounded native workspace; no runtime compilation."""

    def __init__(self, library: Path, *, source_rate_hz: int = 10_000_000):
        self._library = ct.CDLL(str(library))
        if source_rate_hz not in (10_000_000, 15_000_000, 20_000_000):
            raise ValueError("unsupported host decision source rate")
        self._source_rate_hz = source_rate_hz
        self._source_count = source_rate_hz * 120 // 1000
        self._result_version = 1 if source_rate_hz == 10_000_000 else 2
        self._supported_start = {10_000_000: 40, 15_000_000: 34, 20_000_000: 32}[source_rate_hz]
        self._library.leo_host_decision_create_v1.argtypes = [ct.c_void_p, ct.c_size_t]
        self._library.leo_host_decision_create_v1.restype = ct.c_void_p
        self._library.leo_host_decision_destroy_v1.argtypes = [ct.c_void_p]
        self._library.leo_host_decision_destroy_v1.restype = None
        self._library.leo_host_decision_run_v1.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
            ct.POINTER(_Result),
        ]
        self._library.leo_host_decision_run_v1.restype = ct.c_int
        self._library.leo_host_decision_create_v2.argtypes = [
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
        ]
        self._library.leo_host_decision_create_v2.restype = ct.c_void_p
        self._library.leo_host_decision_run_v2.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_uint32,
            ct.POINTER(_Result),
        ]
        self._library.leo_host_decision_run_v2.restype = ct.c_int
        templates = np.ascontiguousarray(
            [
                qin_edge_pilot_frame(2500000, edge, symbol_roll=roll)
                for edge in ("lower", "upper")
                for roll in (0, 17)
            ],
            dtype=np.complex128,
        )
        self._workspace = (
            self._library.leo_host_decision_create_v1(templates.ctypes.data, templates.shape[1])
            if source_rate_hz == 10_000_000
            else self._library.leo_host_decision_create_v2(
                templates.ctypes.data, templates.shape[1], source_rate_hz
            )
        )
        if not self._workspace:
            raise ValueError("host decision workspace rejected its configuration")

    def __enter__(self) -> NativeHostDecision:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._workspace:
            self._library.leo_host_decision_destroy_v1(self._workspace)
            self._workspace = None

    def run(
        self, iq: npt.NDArray[np.int16], *, edge: Literal["lower", "upper"]
    ) -> HostDecisionEvidence:
        if not self._workspace:
            raise ValueError("host decision workspace is closed")
        if (
            not isinstance(iq, np.ndarray)
            or iq.dtype != np.dtype("<i2")
            or iq.shape != (self._source_count, 2)
            or edge not in ("lower", "upper")
        ):
            raise ValueError("host decisions require one complete configured native CI16 dwell")
        values = np.ascontiguousarray(iq)
        result = _Result()
        runner = (
            self._library.leo_host_decision_run_v1
            if self._result_version == 1
            else self._library.leo_host_decision_run_v2
        )
        if runner(
            self._workspace,
            values.ctypes.data,
            len(values),
            int(edge == "upper"),
            ct.byref(result),
        ):
            raise ValueError("native host decision failed; result is unknown")
        if (
            result.version != self._result_version
            or result.reserved
            or result.outcome > 2
            or result.screen_mask != 63
            or result.confirmation_mask not in (1, 2, 4, 8, 16, 32)
            or result.supported_start != self._supported_start
            or result.supported_end != 300000
        ):
            raise ValueError("native host decision returned incompatible evidence")
        return HostDecisionEvidence(
            outcome=("unknown", "detected", "not_detected")[result.outcome],
            screen_mask=result.screen_mask,
            confirmation_mask=result.confirmation_mask,
            supported_start=result.supported_start,
            supported_end=result.supported_end,
            candidate_supported=bool(result.candidate_supported),
            epoch=result.epoch,
            fractional_complete=bool(result.fractional_complete),
            fractional_offset=result.fractional_offset,
            cfo_hz=result.cfo_hz,
            exact_score=result.exact_score,
            margin=result.margin,
            filter_cpu_ms=result.filter_cpu_ms,
            cpu_ms=result.cpu_ms,
            wall_ms=result.wall_ms,
            screen_scores=tuple(result.screen_scores),
        )
