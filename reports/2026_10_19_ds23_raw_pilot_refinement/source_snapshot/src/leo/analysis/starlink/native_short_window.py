"""Reusable production-native GLRT context over exactly 20 ms of captured IQ."""

from __future__ import annotations

import ctypes as ct
import sys
import threading
from typing import Any

import numpy as np


class _Complex(ct.Structure):
    _fields_ = [("real", ct.c_double), ("imaginary", ct.c_double)]


class _Candidate(ct.Structure):
    _fields_ = (
        [
            (name, ct.c_int32)
            for name in [
                "coarse_epoch",
                "coarse_bin",
                "refined_epoch",
                "frame_support",
                "glrt_complete",
                "conditioned_fallback",
                "refinement_skipped",
            ]
        ]
        + [(name, ct.c_double) for name in ["coarse_cfo_hz", "fine_cfo_hz", "conditioned_cfo_hz"]]
        + [("epoch", ct.c_int32)]
        + [
            (name, ct.c_double)
            for name in [
                "acquired_cfo_hz",
                "tracking_cfo_hz",
                "exact_score",
                "control_score",
                "margin",
                "acquire_score",
                "verify_score",
                "verify_control_score",
                "conditioned_score",
                "coarse_score",
            ]
        ]
        + [("fractional_epoch_status", ct.c_int32)]
        + [
            (name, ct.c_double)
            for name in ["fractional_epoch_offset_samples", "fractional_epoch_log_curvature"]
        ]
        + [
            ("fractional_epoch_exact_grid", ct.c_double * 5),
            ("fractional_epoch_control_grid", ct.c_double * 5),
        ]
        + [
            (name, ct.c_double)
            for name in [
                "fractional_exact_score",
                "fractional_control_score",
                "fractional_margin",
                "fractional_residual_cfo_hz",
                "fractional_tracking_cfo_hz",
            ]
        ]
    )


_ROW_COUNTS = [
    "receiver_id",
    "probe_index",
    "probe_start_ms",
    "proposal_executed",
    "proposal_tracking_fallback",
    "proposal_neighbor_matches",
    "candidate_count",
    "retained_peak_count",
    "coarse_gate_skipped_count",
    "conditioned_fallback_count",
    "actual_executed_glrt_calls",
    "glrt_cache_hits",
    "conditioned_cache_hits",
    "fine_fft_cache_entries",
    "fine_fft_cache_hits",
    "fine_precision_calls",
    "fine_precision_guard_checks",
    "fine_precision_fallbacks",
    "fine_precision_nonfinite_fallbacks",
    "fine_precision_near_tie_fallbacks",
    "fine_precision_interpolation_fallbacks",
    "conditioned_bins_screened",
    "conditioned_bins_rechecked",
]
_ROW_TIMINGS = [
    "total_cpu",
    "proposal",
    "stage_sum",
    "proposal_fold",
    "proposal_correlation",
    "proposal_ranking",
    "coarse",
    "acquisition",
    "fine_fft",
    "conditioned",
    "verification",
    "glrt",
    "fractional_epoch",
]


class _Row(ct.Structure):
    _fields_ = (
        [(name, ct.c_int32) for name in _ROW_COUNTS]
        + [(f"{name}_ms", ct.c_double) for name in _ROW_TIMINGS]
        + [("candidates", _Candidate * 8)]
    )


class _Result(ct.Structure):
    _fields_ = [("row_count", ct.c_size_t), ("detector_cpu_ms", ct.c_double), ("rows", _Row * 70)]


def _candidate(value: _Candidate) -> dict[str, Any]:
    result = {
        name: getattr(value, name)
        for name, _ in _Candidate._fields_
        if not name.startswith("fractional_")
    }
    result["conditioned_fallback"] = bool(value.conditioned_fallback)
    result["refinement_skipped"] = bool(value.refinement_skipped)
    if not value.conditioned_fallback:
        result["conditioned_cfo_hz"] = None
        result["conditioned_score"] = None
    if value.refinement_skipped:
        for name in ("acquire_score", "verify_score", "verify_control_score"):
            result[name] = None
    status = value.fractional_epoch_status
    result["fractional_epoch"] = {
        "status": {0: "not_evaluated", 1: "complete", 2: "unbracketed"}[status],
        "exact_score_grid": list(value.fractional_epoch_exact_grid) if status else None,
        "control_score_grid": list(value.fractional_epoch_control_grid) if status else None,
    }
    for public, native in (
        ("offset_samples", "fractional_epoch_offset_samples"),
        ("log_curvature", "fractional_epoch_log_curvature"),
        ("exact_score", "fractional_exact_score"),
        ("control_score", "fractional_control_score"),
        ("margin", "fractional_margin"),
        ("residual_cfo_hz", "fractional_residual_cfo_hz"),
        ("tracking_cfo_hz", "fractional_tracking_cfo_hz"),
    ):
        result["fractional_epoch"][public] = getattr(value, native) if status == 1 else None
    return result


class NativeShortWindow:
    """One reusable C context; file reading and qualification belong to callers.

    Templates must be finite complex128 arrays of the baseline frame length.
    IQ is signed-16 little-endian [sample, receiver, I/Q], with exactly rate/50
    sample times. No receiver or missing sample support is synthesized. The
    lock serializes use and close of this context; distinct contexts remain
    independent. Use as a context manager, or call close explicitly.
    """

    def __init__(
        self,
        library_path: str,
        exact_template: np.ndarray,
        control_template: np.ndarray,
        *,
        sample_rate_hz: int = 2_500_000,
        receiver_count: int = 2,
        fractional_epoch: bool = False,
    ) -> None:
        if sys.byteorder != "little":
            raise ValueError("native CI16 and templates require a little-endian host")
        if sample_rate_hz not in (2_500_000, 5_000_000, 7_500_000, 10_000_000):
            raise ValueError("unsupported native GLRT sample rate")
        if receiver_count not in (1, 2):
            raise ValueError("native GLRT requires one or two receivers")
        count = (sample_rate_hz + 375) // 750
        templates = []
        for template in (exact_template, control_template):
            values = np.asarray(template)
            if values.dtype != np.dtype("<c16") or values.shape != (count,):
                raise ValueError("templates require the exact complex128 baseline frame length")
            if not np.isfinite(values).all():
                raise ValueError("native GLRT templates must be finite")
            templates.append(np.ascontiguousarray(values))
        self.sample_rate_hz = sample_rate_hz
        self.receiver_count = receiver_count
        self.fractional_epoch = fractional_epoch
        self._lock = threading.Lock()
        self._context = ct.c_void_p()
        self._library = ct.CDLL(library_path)
        prefix = "leo_native_glrt" if receiver_count == 2 else "leo_single_rx_glrt"
        create = getattr(self._library, f"{prefix}_create_with_mode")
        create.argtypes = [
            ct.POINTER(ct.c_void_p),
            ct.c_uint32,
            ct.POINTER(_Complex),
            ct.POINTER(_Complex),
            ct.c_size_t,
            ct.c_uint32,
        ]
        create.restype = ct.c_int
        self._analyze = getattr(self._library, f"{prefix}_analyze_short_window")
        self._analyze.argtypes = [
            ct.c_void_p,
            ct.POINTER(ct.c_int16),
            ct.c_size_t,
            ct.POINTER(_Result),
        ]
        self._analyze.restype = ct.c_int
        self._destroy = getattr(self._library, f"{prefix}_destroy")
        self._destroy.argtypes = [ct.c_void_p]
        self._destroy.restype = ct.c_int
        self._status = self._library.leo_native_glrt_status_string
        self._status.argtypes = [ct.c_int]
        self._status.restype = ct.c_char_p
        status = create(
            ct.byref(self._context),
            sample_rate_hz,
            *(template.ctypes.data_as(ct.POINTER(_Complex)) for template in templates),
            count,
            int(fractional_epoch),
        )
        self._check(status)

    def _check(self, status: int) -> None:
        if status:
            raise RuntimeError(f"native GLRT: {self._status(status).decode()}")

    def analyze(self, samples: np.ndarray, *, include_timings: bool = False) -> dict[str, Any]:
        values = np.asarray(samples)
        count = self.sample_rate_hz // 50
        if (
            values.dtype != np.dtype("<i2")
            or values.shape != (count, self.receiver_count, 2)
            or not values.flags.c_contiguous
        ):
            raise ValueError("native GLRT requires exactly 20 ms of contiguous CI16 per receiver")
        with self._lock:
            if not self._context.value:
                raise RuntimeError("native GLRT context is closed")
            result = _Result()
            self._check(
                self._analyze(
                    self._context,
                    values.ctypes.data_as(ct.POINTER(ct.c_int16)),
                    count,
                    ct.byref(result),
                )
            )
            if result.row_count != self.receiver_count:
                raise RuntimeError("native GLRT returned unexpected short-window geometry")
            rows = []
            for value in result.rows[: result.row_count]:
                if not 0 <= value.candidate_count <= 8:
                    raise RuntimeError("native GLRT returned invalid candidate count")
                row = {name: getattr(value, name) for name in _ROW_COUNTS}
                row["candidates"] = [
                    _candidate(candidate) for candidate in value.candidates[: value.candidate_count]
                ]
                if include_timings:
                    row["timings_ms"] = {
                        name: getattr(value, f"{name}_ms") for name in _ROW_TIMINGS
                    }
                rows.append(row)
            document: dict[str, Any] = {
                "schema": "leo-native-glrt-short-window/v1",
                "algorithm_id": "wave8-gate314-source-v1",
                "sample_rate_hz": self.sample_rate_hz,
                "dwell_ms": 20,
                "probe_ms": 20,
                "probe_stride_ms": 20,
                "receiver_count": self.receiver_count,
                "input_complex_times": count,
                "window_start_sample": 0,
                "window_end_sample_exclusive": count,
                "refinement_mode": "ordinary-with-fractional-epoch"
                if self.fractional_epoch
                else "ordinary",
                "rows": rows,
            }
            if include_timings:
                document["detector_cpu_ms"] = result.detector_cpu_ms
            return document

    def close(self) -> None:
        with self._lock:
            if self._context.value:
                self._check(self._destroy(self._context))
                self._context = ct.c_void_p()

    def __enter__(self) -> NativeShortWindow:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
