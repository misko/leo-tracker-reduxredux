"""Original-anchor CFO callback, no acquisition and no admission changes."""

import importlib.util
import time
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import (
    _conditioned_correlation_workspace,
    conditioned_glrt64_score,
)
from leo.contracts.states import StarlinkEdge

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "frozen125_refine", HERE.parent / "2026_10_09_position_error_iter125/refine.py"
)
refinement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refinement)


def circular_change(candidate, baseline):
    period = 512 * refinement.DELTA_HZ
    raw = float(candidate - baseline)
    circular = (raw + period / 2) % period - period / 2
    return {
        "raw_hz": raw,
        "circular_hz": circular,
        "wrap_count": int(round((raw - circular) / period)),
    }


def evaluate(probe, window, sample_rate_hz, *, native=None):
    if sample_rate_hz not in (2_500_000, 10_000_000):
        raise ValueError("unsupported sample rate")
    started = time.perf_counter()
    if native is None:
        scored = conditioned_glrt64_score(
            probe,
            sample_rate_hz,
            epoch_sample=window.epoch_sample,
            acquired_cfo_hz=window.acquired_cfo_hz,
            edge=window.edge,
            fractional_epoch_offset_samples=window.offset_samples,
        )
        exact, control, residual = scored.exact_score, scored.control_score, scored.residual_cfo_hz
        scorer_kind = "original-python-conditioned-scorer"
    else:
        exact, control, residual = native.glrt(
            probe, window.epoch_sample, window.acquired_cfo_hz, window.offset_samples
        )
        scorer_kind = "native-presence-differential-oracle"
    frequency = window.acquired_cfo_hz + residual
    if not np.isfinite([exact, control, frequency]).all():
        raise ValueError("nonfinite native output")
    if max(abs(exact - window.original_exact), abs(control - window.original_control)) > 1e-10:
        raise ValueError("original/native score parity failure")
    if abs(frequency - window.original_cfo_hz) > 1e-6:
        raise ValueError("original/native CFO parity failure")
    workspace = _conditioned_correlation_workspace(
        probe,
        sample_rate_hz,
        window.epoch_sample,
        window.acquired_cfo_hz,
        selected_symbols=np.arange(2, 66),
        edge=StarlinkEdge(window.edge),
        fractional_epoch_offset_samples=window.offset_samples,
    )
    z = workspace.select(np.arange(2, 66))
    if abs(z.symbol_step_s - 4.4e-6) > 1e-15:
        raise ValueError("unsupported symbol geometry")
    result = refinement.refine(
        z.values, native_bin=int(round(residual / refinement.DELTA_HZ)) % 512
    )
    if abs(result["coarse_score"] - exact) > 1e-10 or abs(result["coarse_hz"] - residual) > 1e-6:
        raise ValueError("native/Python spectrum parity failure")
    return {
        "scorer_kind": scorer_kind,
        "baseline_cfo_hz": float(frequency),
        "logparabola_cfo_hz": window.acquired_cfo_hz + result["logparabola_hz"],
        "newton_cfo_hz": window.acquired_cfo_hz + result["newton_hz"],
        "changes": {
            name: circular_change(result[f"{name}_hz"], residual)
            for name in ("logparabola", "newton")
        },
        "original_passed": window.original_passed,
        "refinement": result,
        "elapsed_s": time.perf_counter() - started,
        "parity": "passed",
    }
