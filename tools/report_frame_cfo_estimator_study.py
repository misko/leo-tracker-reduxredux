#!/usr/bin/env python3
"""Benchmark robust per-frame Qin edge-pilot CFO estimators."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.qam.pilot import (  # noqa: E402
    _complete_frame_starts,
    _fit_phase_slope_frame,
    _frequency_coherence,
    _frequency_likelihood,
    _KnownPilotDemodulator,
    _tone_deletion_frequency_spread,
)
from leo.analysis.research.frame_cfo import (  # noqa: E402
    differential_phase_cfo,
    ordinary_profile_cfo,
    robust_profile_cfo,
)
from leo.analysis.starlink import (  # noqa: E402
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_symbols,
)
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

try:  # noqa: E402
    import report_edge_pilot_phase_slope_figures as source
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import report_edge_pilot_phase_slope_figures as source


DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_frame_cfo_estimator_study")
DEFAULT_REPORT = Path("reports/2026_08_24_frame_cfo_estimator_study.md")
INK = "#17354a"
BLUE = "#2f83b7"
GREEN = "#3f8f67"
AMBER = "#d9881f"
PURPLE = "#7b65a8"
RED = "#bd5b52"
GRAY = "#94a2aa"
METHOD_COLORS = {
    "discrete-25Hz": GRAY,
    "parabolic-profile": BLUE,
    "phase-refined-profile": GREEN,
    "robust-profile": AMBER,
    "differential-phase": PURPLE,
}


@dataclass(frozen=True, slots=True)
class RawFrameComparison:
    window_index: int
    frame_index: int
    time_s: float
    source_cfo_hz: float
    discrete_cfo_hz: float
    parabolic_cfo_hz: float
    phase_refined_cfo_hz: float
    robust_cfo_hz: float
    differential_cfo_hz: float
    odd_profile_cfo_hz: float
    full_profile_cfo_hz: float
    even_exact_coherence: float
    even_control_coherence: float
    odd_exact_at_discrete: float
    odd_exact_at_parabolic: float
    odd_exact_at_phase_refined: float
    odd_exact_at_robust: float
    odd_exact_maximum: float
    odd_control_at_phase_refined: float
    even_frequency_uncertainty_hz: float
    odd_frequency_uncertainty_hz: float
    robust_frequency_uncertainty_hz: float
    robust_downweighted_fraction: float
    robust_effective_symbol_count: float
    full_search_boundary: bool
    timing_minus_one_cfo_hz: float
    timing_plus_one_cfo_hz: float
    tone_deletion_spread_hz: float

    @property
    def qualified(self) -> bool:
        return bool(
            self.even_exact_coherence >= 0.02
            and self.even_exact_coherence >= self.even_control_coherence
            and not self.full_search_boundary
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-root", type=Path, default=source.DEFAULT_ANALYSIS_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--maximum-windows", type=int, default=16)
    parser.add_argument("--synthetic-replicates", type=int, default=40)
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return document


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _stratified_windows(
    windows: tuple[source.SelectedWindow, ...], maximum_windows: int
) -> tuple[source.SelectedWindow, ...]:
    if maximum_windows < 1:
        raise ValueError("maximum windows must be positive")
    if len(windows) <= maximum_windows:
        return windows
    indexes = np.unique(np.rint(np.linspace(0, len(windows) - 1, maximum_windows)).astype(int))
    return tuple(windows[int(index)] for index in indexes)


def _discrete_profile(
    matched: np.ndarray,
    times_s: np.ndarray,
    *,
    maximum_residual_cfo_hz: float,
    step_hz: float = 25.0,
) -> float:
    cells = round(2.0 * maximum_residual_cfo_hz / step_hz)
    grid = np.linspace(-maximum_residual_cfo_hz, maximum_residual_cfo_hz, cells + 1)
    power = _frequency_likelihood(matched, times_s, grid)
    return float(grid[int(np.argmax(power))])


def _raw_comparisons(
    *,
    bulk_root: Path,
    analysis_root: Path,
    maximum_windows: int,
) -> tuple[tuple[RawFrameComparison, ...], dict[str, Any]]:
    scan_path = analysis_root / "standard.pilot-scan.v3.json"
    bank_path = analysis_root / "standard.final-trajectory-bank.v2.json"
    scan = source._load_json(scan_path)
    trajectory = source._trajectory(source._load_json(bank_path))
    accepted = source._select_windows(
        scan,
        trajectory,
        start_s=33.7,
        end_s=37.7,
        minimum_margin=0.05,
        maximum_model_error_hz=2_500.0,
        accepted_stride=1,
    )
    windows = _stratified_windows(accepted, maximum_windows)
    if not windows:
        raise ValueError("raw benchmark selected no timing locks")
    sample_rate_hz = 2_500_000.0
    probe_samples = int(scan["probe_samples"])
    expected = qin_edge_pilot_symbols(StarlinkEdge.UPPER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.UPPER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    times = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times -= np.mean(times)
    even = np.arange(0, 300, 2, dtype=int)
    odd = np.arange(1, 300, 2, dtype=int)
    frame_starts = _complete_frame_starts(probe_samples, sample_rate_hz, 0)
    output: list[RawFrameComparison] = []
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
        bundle = store.inspect(source.SESSION_ID)
        reader = store.reader(bundle, "stream-0", verify=True)
        if reader.sample_rate_hz != round(sample_rate_hz):
            raise ValueError("frame-CFO benchmark requires the source 2.5 MS/s recording")
        for window_index, window in enumerate(windows):
            raw = reader.read(
                window.aligned_sample_start - 1,
                probe_samples + 2,
                receiver_ids=(0,),
            )
            iq = source._complex_receiver(raw)
            demodulator = _KnownPilotDemodulator(
                iq,
                sample_rate_hz,
                StarlinkEdge.UPPER,
                window.glrt64_cfo_hz,
            )
            nominal = np.asarray(
                [demodulator.frame(start + 1) for start in frame_starts],
                dtype=np.complex128,
            )
            timing_minus = np.asarray(
                [demodulator.frame(start) for start in frame_starts],
                dtype=np.complex128,
            )
            timing_plus = np.asarray(
                [demodulator.frame(start + 2) for start in frame_starts],
                dtype=np.complex128,
            )
            for frame_index, pilot in enumerate(nominal):
                exact = pilot * np.conj(expected)
                null = pilot * np.conj(control)
                even_exact = exact[even]
                even_control = null[even]
                odd_exact = exact[odd]
                odd_control = null[odd]
                even_fit = _fit_phase_slope_frame(
                    even_exact,
                    even_control,
                    times[even],
                    maximum_residual_cfo_hz=2_000.0,
                )
                odd_fit = _fit_phase_slope_frame(
                    odd_exact,
                    odd_control,
                    times[odd],
                    maximum_residual_cfo_hz=2_000.0,
                )
                full_fit = _fit_phase_slope_frame(
                    exact,
                    null,
                    times,
                    maximum_residual_cfo_hz=2_000.0,
                )
                robust = robust_profile_cfo(
                    even_exact,
                    times[even],
                    maximum_residual_cfo_hz=2_000.0,
                    maximum_iterations=3,
                )
                discrete = _discrete_profile(
                    even_exact,
                    times[even],
                    maximum_residual_cfo_hz=2_000.0,
                )
                parabolic = ordinary_profile_cfo(
                    even_exact,
                    times[even],
                    maximum_residual_cfo_hz=2_000.0,
                    coarse_step_hz=25.0,
                    fine_step_hz=25.0,
                )
                differential = differential_phase_cfo(
                    even_exact,
                    times[even],
                    maximum_residual_cfo_hz=2_000.0,
                )
                shifted_fits = []
                for shifted in (timing_minus[frame_index], timing_plus[frame_index]):
                    shifted_exact = shifted * np.conj(expected)
                    shifted_null = shifted * np.conj(control)
                    shifted_fits.append(
                        _fit_phase_slope_frame(
                            shifted_exact,
                            shifted_null,
                            times,
                            maximum_residual_cfo_hz=2_000.0,
                        ).residual_cfo_hz
                    )
                absolute_offset = window.glrt64_cfo_hz
                output.append(
                    RawFrameComparison(
                        window_index=window_index,
                        frame_index=frame_index,
                        time_s=float(
                            (
                                window.aligned_sample_start
                                + frame_starts[frame_index]
                                + np.mean((np.arange(300) + 2.5) * OFDM_SYMBOL_DURATION_S)
                                * sample_rate_hz
                            )
                            / sample_rate_hz
                        ),
                        source_cfo_hz=absolute_offset,
                        discrete_cfo_hz=absolute_offset + discrete,
                        parabolic_cfo_hz=absolute_offset + parabolic.frequency_hz,
                        phase_refined_cfo_hz=absolute_offset + even_fit.residual_cfo_hz,
                        robust_cfo_hz=absolute_offset + robust.frequency_hz,
                        differential_cfo_hz=absolute_offset + differential,
                        odd_profile_cfo_hz=absolute_offset + odd_fit.residual_cfo_hz,
                        full_profile_cfo_hz=absolute_offset + full_fit.residual_cfo_hz,
                        even_exact_coherence=even_fit.exact_coherence,
                        even_control_coherence=even_fit.control_coherence,
                        odd_exact_at_discrete=_frequency_coherence(odd_exact, times[odd], discrete),
                        odd_exact_at_parabolic=_frequency_coherence(
                            odd_exact, times[odd], parabolic.frequency_hz
                        ),
                        odd_exact_at_phase_refined=_frequency_coherence(
                            odd_exact, times[odd], even_fit.residual_cfo_hz
                        ),
                        odd_exact_at_robust=_frequency_coherence(
                            odd_exact, times[odd], robust.frequency_hz
                        ),
                        odd_exact_maximum=odd_fit.exact_coherence,
                        odd_control_at_phase_refined=_frequency_coherence(
                            odd_control, times[odd], even_fit.residual_cfo_hz
                        ),
                        even_frequency_uncertainty_hz=even_fit.frequency_uncertainty_hz,
                        odd_frequency_uncertainty_hz=odd_fit.frequency_uncertainty_hz,
                        robust_frequency_uncertainty_hz=robust.frequency_uncertainty_hz,
                        robust_downweighted_fraction=robust.heavily_downweighted_symbol_fraction,
                        robust_effective_symbol_count=robust.effective_symbol_count,
                        full_search_boundary=bool(
                            abs(abs(full_fit.residual_cfo_hz) - 2_000.0) <= 0.05
                        ),
                        timing_minus_one_cfo_hz=absolute_offset + shifted_fits[0],
                        timing_plus_one_cfo_hz=absolute_offset + shifted_fits[1],
                        tone_deletion_spread_hz=_tone_deletion_frequency_spread(
                            exact,
                            times,
                            full_fit.residual_cfo_hz,
                            maximum_residual_cfo_hz=2_000.0,
                        ),
                    )
                )
            print(
                f"raw frame CFO: {window_index + 1}/{len(windows)} timing locks",
                flush=True,
            )
    finally:
        if store is not None:
            store.close()
    provenance = {
        "session_id": source.SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "edge": "upper",
        "recording_manifest_path": str(bundle.path / "manifest.json"),
        "recording_manifest_sha256": bundle.manifest_sha256,
        "analysis_root": str(analysis_root),
        "pilot_scan_path": str(scan_path),
        "pilot_scan_sha256": _sha256(scan_path),
        "final_trajectory_bank_path": str(bank_path),
        "final_trajectory_bank_sha256": _sha256(bank_path),
        "accepted_window_count": len(accepted),
        "benchmarked_window_count": len(windows),
        "benchmarked_window_detection_times_s": [item.detection_time_s for item in windows],
        "frame_count": len(output),
    }
    return tuple(output), provenance


def _synthetic_frame(
    generator: np.random.Generator,
    *,
    frequency_hz: float,
    noise_sigma: float,
    scenario: str,
) -> tuple[np.ndarray, np.ndarray]:
    times = (np.arange(300, dtype=float) - 149.5) * OFDM_SYMBOL_DURATION_S
    channel = generator.uniform(0.45, 1.55, size=8) * np.exp(
        1j * generator.uniform(-np.pi, np.pi, size=8)
    )
    values = channel[None, :] * np.exp(2j * np.pi * frequency_hz * times[:, None])
    values += (
        noise_sigma
        / np.sqrt(2.0)
        * (generator.normal(size=values.shape) + 1j * generator.normal(size=values.shape))
    )
    if scenario == "15% symbol outliers":
        indexes = generator.choice(len(times), size=45, replace=False)
        values[indexes] += 3.5 * np.exp(
            1j * generator.uniform(-np.pi, np.pi, size=(len(indexes), 8))
        )
    elif scenario == "one coherent tone spur":
        tone = int(generator.integers(0, 8))
        spur_frequency = frequency_hz + generator.choice((-1_200.0, 1_200.0))
        values[:, tone] += 4.5 * np.exp(
            1j * (generator.uniform(-np.pi, np.pi) + 2.0 * np.pi * spur_frequency * times)
        )
    return values, times


def _synthetic_benchmark(replicates: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if replicates < 5:
        raise ValueError("synthetic benchmark needs at least five replicates")
    generator = np.random.default_rng(0xCF0_2026)
    scenarios = (
        ("clean high SNR", 0.12),
        ("clean medium SNR", 0.35),
        ("clean low SNR", 0.80),
        ("15% symbol outliers", 0.25),
        ("one coherent tone spur", 0.25),
    )
    rows: list[dict[str, Any]] = []
    raw: dict[str, dict[str, list[float]]] = {}
    exact_symbols = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control_symbols = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    control_wipeoff = exact_symbols * np.conj(control_symbols)
    coherent_spur_diagnostics: list[dict[str, Any]] = []
    for scenario, noise in scenarios:
        results = {
            method: {"error": [], "sigma": []}
            for method in (
                "discrete-25Hz",
                "parabolic-profile",
                "robust-profile",
                "differential-phase",
            )
        }
        for _ in range(replicates):
            truth = float(generator.uniform(-1_500.0, 1_500.0))
            values, times = _synthetic_frame(
                generator,
                frequency_hz=truth,
                noise_sigma=noise,
                scenario=scenario,
            )
            discrete = _discrete_profile(
                values,
                times,
                maximum_residual_cfo_hz=2_000.0,
            )
            parabolic = ordinary_profile_cfo(
                values,
                times,
                maximum_residual_cfo_hz=2_000.0,
                coarse_step_hz=25.0,
                fine_step_hz=25.0,
            )
            robust = robust_profile_cfo(
                values,
                times,
                maximum_residual_cfo_hz=2_000.0,
                maximum_iterations=3,
            )
            differential = differential_phase_cfo(
                values,
                times,
                maximum_residual_cfo_hz=2_000.0,
            )
            if scenario == "one coherent tone spur":
                null = values * control_wipeoff
                full_gate_fit = _fit_phase_slope_frame(
                    values,
                    null,
                    times,
                    maximum_residual_cfo_hz=2_000.0,
                )
                even_fit = _fit_phase_slope_frame(
                    values[::2],
                    null[::2],
                    times[::2],
                    maximum_residual_cfo_hz=2_000.0,
                )
                odd_fit = _fit_phase_slope_frame(
                    values[1::2],
                    null[1::2],
                    times[1::2],
                    maximum_residual_cfo_hz=2_000.0,
                )
                half_fits = tuple(
                    _fit_phase_slope_frame(
                        values[indexes],
                        null[indexes],
                        times[indexes],
                        maximum_residual_cfo_hz=2_000.0,
                    )
                    for indexes in (slice(0, 150), slice(150, 300))
                )
                half_z = abs(half_fits[0].residual_cfo_hz - half_fits[1].residual_cfo_hz) / max(
                    math.hypot(
                        half_fits[0].frequency_uncertainty_hz,
                        half_fits[1].frequency_uncertainty_hz,
                    ),
                    np.finfo(float).tiny,
                )
                deletion_spread = _tone_deletion_frequency_spread(
                    values,
                    times,
                    full_gate_fit.residual_cfo_hz,
                    maximum_residual_cfo_hz=2_000.0,
                )
                baseline_pass = bool(
                    full_gate_fit.exact_coherence >= 0.02
                    and full_gate_fit.exact_coherence >= full_gate_fit.control_coherence
                    and abs(even_fit.residual_cfo_hz - odd_fit.residual_cfo_hz) <= 100.0
                    and half_z <= 4.0
                    and abs(abs(full_gate_fit.residual_cfo_hz) - 2_000.0) > 0.05
                )
                coherent_spur_diagnostics.append(
                    {
                        "ordinary_error_hz": float(full_gate_fit.residual_cfo_hz - truth),
                        "baseline_gates_pass": baseline_pass,
                        "tone_deletion_spread_hz": deletion_spread,
                    }
                )
            estimates = {
                "discrete-25Hz": (discrete, math.nan),
                "parabolic-profile": (
                    parabolic.frequency_hz,
                    parabolic.frequency_uncertainty_hz,
                ),
                "robust-profile": (
                    robust.frequency_hz,
                    robust.frequency_uncertainty_hz,
                ),
                "differential-phase": (differential, math.nan),
            }
            for method, (estimate, sigma) in estimates.items():
                results[method]["error"].append(float(estimate - truth))
                results[method]["sigma"].append(float(sigma))
        raw[scenario] = results
        for method, values in results.items():
            errors = np.asarray(values["error"], dtype=float)
            sigmas = np.asarray(values["sigma"], dtype=float)
            finite_sigma = np.isfinite(sigmas) & (sigmas > 0.0)
            rows.append(
                {
                    "scenario": scenario,
                    "method": method,
                    "replicate_count": replicates,
                    "bias_hz": float(np.mean(errors)),
                    "rmse_hz": float(np.sqrt(np.mean(errors**2))),
                    "p95_absolute_error_hz": float(np.percentile(np.abs(errors), 95)),
                    "failure_over_100_hz_fraction": float(np.mean(np.abs(errors) > 100.0)),
                    "median_reported_sigma_hz": (
                        float(np.median(sigmas[finite_sigma])) if np.any(finite_sigma) else None
                    ),
                    "nominal_95_percent_coverage": (
                        float(np.mean(np.abs(errors[finite_sigma]) <= 1.96 * sigmas[finite_sigma]))
                        if np.any(finite_sigma)
                        else None
                    ),
                }
            )

    step_differences = []
    stationary_differences = []
    for stepped in (False, True):
        for _ in range(replicates):
            center = float(generator.uniform(-1_200.0, 1_200.0))
            values, times = _synthetic_frame(
                generator,
                frequency_hz=center,
                noise_sigma=0.30,
                scenario="clean medium SNR",
            )
            if stepped:
                values[150:] *= np.exp(2j * np.pi * 300.0 * times[150:, None])
            halves = []
            for indexes in (np.arange(0, 150), np.arange(150, 300)):
                halves.append(
                    ordinary_profile_cfo(
                        values[indexes],
                        times[indexes],
                        maximum_residual_cfo_hz=2_000.0,
                    ).frequency_hz
                )
            difference = abs(halves[1] - halves[0])
            (step_differences if stepped else stationary_differences).append(difference)
    step = {
        "injected_step_hz": 300.0,
        "stationary_median_split_difference_hz": float(np.median(stationary_differences)),
        "stepped_median_split_difference_hz": float(np.median(step_differences)),
        "threshold_hz": 150.0,
        "false_alarm_fraction": float(np.mean(np.asarray(stationary_differences) > 150.0)),
        "detection_fraction": float(np.mean(np.asarray(step_differences) > 150.0)),
    }
    failures = tuple(
        item for item in coherent_spur_diagnostics if abs(item["ordinary_error_hz"]) > 100.0
    )
    false_accepts = tuple(item for item in failures if item["baseline_gates_pass"])
    step["coherent_one_tone_influence_test"] = {
        "trial_count": len(coherent_spur_diagnostics),
        "ordinary_failure_over_100_hz_count": len(failures),
        "baseline_gate_false_accept_count": len(false_accepts),
        "maximum_tone_deletion_shift_hz": 75.0,
        "ordinary_failures_caught_count": sum(
            item["tone_deletion_spread_hz"] > 75.0 for item in failures
        ),
        "baseline_false_accepts_caught_count": sum(
            item["tone_deletion_spread_hz"] > 75.0 for item in false_accepts
        ),
        "minimum_failure_tone_deletion_spread_hz": (
            float(min(item["tone_deletion_spread_hz"] for item in failures)) if failures else None
        ),
    }
    return rows, step


def _summary(values: tuple[RawFrameComparison, ...]) -> dict[str, Any]:
    selected = tuple(item for item in values if item.qualified)
    if not selected:
        raise ValueError("no raw frames pass the declared Qin gate")
    methods = {
        "discrete-25Hz": "discrete_cfo_hz",
        "parabolic-profile": "parabolic_cfo_hz",
        "phase-refined-profile": "phase_refined_cfo_hz",
        "robust-profile": "robust_cfo_hz",
        "differential-phase": "differential_cfo_hz",
    }
    rows = []
    for name, field in methods.items():
        estimate = np.asarray([getattr(item, field) for item in selected], dtype=float)
        odd = np.asarray([item.odd_profile_cfo_hz for item in selected], dtype=float)
        differences = estimate - odd
        heldout_field = {
            "discrete-25Hz": "odd_exact_at_discrete",
            "parabolic-profile": "odd_exact_at_parabolic",
            "phase-refined-profile": "odd_exact_at_phase_refined",
            "robust-profile": "odd_exact_at_robust",
        }.get(name)
        efficiency = None
        if heldout_field is not None:
            score = np.asarray([getattr(item, heldout_field) for item in selected], dtype=float)
            maximum = np.asarray([item.odd_exact_maximum for item in selected], dtype=float)
            efficiency = score / np.maximum(maximum, np.finfo(float).tiny)
        rows.append(
            {
                "method": name,
                "frame_count": len(selected),
                "even_minus_odd_bias_hz": float(np.mean(differences)),
                "even_minus_odd_rms_hz": float(np.sqrt(np.mean(differences**2))),
                "even_minus_odd_median_absolute_hz": float(np.median(np.abs(differences))),
                "even_minus_odd_p95_absolute_hz": float(np.percentile(np.abs(differences), 95)),
                "within_100_hz_fraction": float(np.mean(np.abs(differences) <= 100.0)),
                "median_heldout_likelihood_efficiency": (
                    None if efficiency is None else float(np.median(efficiency))
                ),
                "p10_heldout_likelihood_efficiency": (
                    None if efficiency is None else float(np.percentile(efficiency, 10))
                ),
            }
        )
    even = np.asarray([item.phase_refined_cfo_hz for item in selected], dtype=float)
    odd = np.asarray([item.odd_profile_cfo_hz for item in selected], dtype=float)
    even_sigma = np.asarray([item.even_frequency_uncertainty_hz for item in selected], dtype=float)
    odd_sigma = np.asarray([item.odd_frequency_uncertainty_hz for item in selected], dtype=float)
    conditional_sigma = np.sqrt(even_sigma**2 + odd_sigma**2)
    timing_minus = np.asarray([item.timing_minus_one_cfo_hz for item in selected], dtype=float)
    timing_plus = np.asarray([item.timing_plus_one_cfo_hz for item in selected], dtype=float)
    full = np.asarray([item.full_profile_cfo_hz for item in selected], dtype=float)
    discrete = np.asarray([item.discrete_cfo_hz for item in selected], dtype=float)
    parabolic = np.asarray([item.parabolic_cfo_hz for item in selected], dtype=float)
    robust = np.asarray([item.robust_cfo_hz for item in selected], dtype=float)
    tone_deletion = np.asarray(
        [item.tone_deletion_spread_hz for item in selected],
        dtype=float,
    )
    robust_score = np.asarray([item.odd_exact_at_robust for item in selected], dtype=float)
    ordinary_score = np.asarray([item.odd_exact_at_phase_refined for item in selected], dtype=float)
    return {
        "raw_frame_count": len(values),
        "qualified_frame_count": len(selected),
        "qualification": (
            "even exact coherence >= 0.02, exact >= rolled control, no full-profile boundary"
        ),
        "methods": rows,
        "split_fold_disagreement": {
            "median_absolute_hz": float(np.median(np.abs(even - odd))),
            "p95_absolute_hz": float(np.percentile(np.abs(even - odd), 95)),
            "over_100_hz_fraction": float(np.mean(np.abs(even - odd) > 100.0)),
        },
        "conditional_uncertainty_calibration": {
            "nominal_95_percent_coverage": float(
                np.mean(np.abs(even - odd) <= 1.96 * conditional_sigma)
            ),
            "standardized_difference_rms": float(
                np.sqrt(np.mean(((even - odd) / conditional_sigma) ** 2))
            ),
            "median_predicted_split_sigma_hz": float(np.median(conditional_sigma)),
            "empirical_split_rms_hz": float(np.sqrt(np.mean((even - odd) ** 2))),
        },
        "sub_bin_refinement": {
            "median_absolute_correction_hz": float(np.median(np.abs(parabolic - discrete))),
            "p95_absolute_correction_hz": float(np.percentile(np.abs(parabolic - discrete), 95)),
            "heldout_score_improved_fraction": float(
                np.mean(
                    np.asarray([item.odd_exact_at_parabolic for item in selected])
                    > np.asarray([item.odd_exact_at_discrete for item in selected])
                )
            ),
        },
        "timing_sensitivity": {
            "minus_one_sample_median_absolute_hz": float(np.median(np.abs(timing_minus - full))),
            "plus_one_sample_median_absolute_hz": float(np.median(np.abs(timing_plus - full))),
            "worst_shift_p95_absolute_hz": float(
                np.percentile(
                    np.maximum(np.abs(timing_minus - full), np.abs(timing_plus - full)), 95
                )
            ),
            "worst_shift_maximum_absolute_hz": float(
                np.max(np.maximum(np.abs(timing_minus - full), np.abs(timing_plus - full)))
            ),
        },
        "robust_weighting": {
            "median_heavily_downweighted_symbol_fraction": float(
                np.median([item.robust_downweighted_fraction for item in selected])
            ),
            "median_effective_symbol_count": float(
                np.median([item.robust_effective_symbol_count for item in selected])
            ),
            "median_absolute_cfo_change_hz": float(np.median(np.abs(robust - even))),
            "p95_absolute_cfo_change_hz": float(np.percentile(np.abs(robust - even), 95)),
            "heldout_score_improved_fraction": float(np.mean(robust_score > ordinary_score)),
        },
        "tone_deletion_influence": {
            "maximum_allowed_shift_hz": 75.0,
            "median_spread_hz": float(np.median(tone_deletion)),
            "p95_spread_hz": float(np.percentile(tone_deletion, 95)),
            "maximum_spread_hz": float(np.max(tone_deletion)),
            "over_gate_fraction": float(np.mean(tone_deletion > 75.0)),
        },
    }


def _cdf(axis, values: np.ndarray, *, label: str, color: str) -> None:
    ordered = np.sort(np.asarray(values, dtype=float))
    axis.plot(ordered, np.arange(1, len(ordered) + 1) / len(ordered), label=label, color=color)


def _plot_real(values: tuple[RawFrameComparison, ...], path: Path) -> None:
    selected = tuple(item for item in values if item.qualified)
    odd = np.asarray([item.odd_profile_cfo_hz for item in selected], dtype=float)
    figure = Figure(figsize=(13.5, 8.2), constrained_layout=True)
    axes = figure.subplots(2, 2)
    for name, field in (
        ("discrete-25Hz", "discrete_cfo_hz"),
        ("parabolic-profile", "parabolic_cfo_hz"),
        ("phase-refined-profile", "phase_refined_cfo_hz"),
        ("robust-profile", "robust_cfo_hz"),
        ("differential-phase", "differential_cfo_hz"),
    ):
        estimate = np.asarray([getattr(item, field) for item in selected], dtype=float)
        _cdf(
            axes[0, 0],
            np.abs(estimate - odd),
            label=name,
            color=METHOD_COLORS[name],
        )
    axes[0, 0].set_xlim(0, 400)
    axes[0, 0].set_xlabel("|even-trained CFO − odd-symbol CFO| (Hz)")
    axes[0, 0].set_ylabel("empirical cumulative fraction")
    axes[0, 0].set_title("A · Independent split-fold repeatability", loc="left", fontweight="bold")
    axes[0, 0].legend(fontsize=8)

    maximum = np.asarray([item.odd_exact_maximum for item in selected], dtype=float)
    for name, field in (
        ("discrete-25Hz", "odd_exact_at_discrete"),
        ("parabolic-profile", "odd_exact_at_parabolic"),
        ("phase-refined-profile", "odd_exact_at_phase_refined"),
        ("robust-profile", "odd_exact_at_robust"),
    ):
        efficiency = np.asarray([getattr(item, field) for item in selected]) / np.maximum(
            maximum, np.finfo(float).tiny
        )
        _cdf(
            axes[0, 1],
            efficiency,
            label=name,
            color=METHOD_COLORS[name],
        )
    axes[0, 1].set_xlim(0, 1.02)
    axes[0, 1].set_xlabel("held-out odd likelihood / odd-symbol maximum")
    axes[0, 1].set_ylabel("empirical cumulative fraction")
    axes[0, 1].set_title("B · Independent predictive likelihood", loc="left", fontweight="bold")
    axes[0, 1].legend(fontsize=8)

    full = np.asarray([item.full_profile_cfo_hz for item in selected])
    minus = np.asarray([item.timing_minus_one_cfo_hz for item in selected]) - full
    plus = np.asarray([item.timing_plus_one_cfo_hz for item in selected]) - full
    axes[1, 0].hist(minus, bins=45, alpha=0.65, color=BLUE, label="epoch −1 sample")
    axes[1, 0].hist(plus, bins=45, alpha=0.65, color=AMBER, label="epoch +1 sample")
    axes[1, 0].axvline(0.0, color=INK, linewidth=1)
    axes[1, 0].set_xlabel("full-profile CFO change (Hz)")
    axes[1, 0].set_ylabel("frame count")
    axes[1, 0].set_title("C · Timing ±1-sample sensitivity", loc="left", fontweight="bold")
    axes[1, 0].legend(fontsize=8)

    ordinary = np.asarray([item.phase_refined_cfo_hz for item in selected])
    robust = np.asarray([item.robust_cfo_hz for item in selected])
    score_delta = np.asarray([item.odd_exact_at_robust for item in selected]) - np.asarray(
        [item.odd_exact_at_phase_refined for item in selected]
    )
    downweighted = np.asarray([item.robust_downweighted_fraction for item in selected])
    points = axes[1, 1].scatter(
        robust - ordinary,
        score_delta,
        c=downweighted,
        cmap="viridis",
        vmin=0.0,
        vmax=max(0.1, float(np.max(downweighted))),
        s=24,
        alpha=0.72,
    )
    axes[1, 1].axhline(0.0, color=INK, linewidth=1)
    axes[1, 1].axvline(0.0, color=INK, linewidth=1)
    axes[1, 1].set_xlabel("robust − ordinary even-trained CFO (Hz)")
    axes[1, 1].set_ylabel("held-out odd-likelihood change")
    axes[1, 1].set_title(
        "D · Robust changes must earn held-out gain", loc="left", fontweight="bold"
    )
    figure.colorbar(points, ax=axes[1, 1], label="fraction of symbols weight < 0.5")
    figure.suptitle(
        f"Real-IQ per-frame CFO estimator audit · {len(selected)}/{len(values)} qualified frames",
        fontsize=16,
        fontweight="bold",
        color=INK,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def _plot_synthetic(rows: list[dict[str, Any]], step: dict[str, Any], path: Path) -> None:
    scenarios = list(dict.fromkeys(str(row["scenario"]) for row in rows))
    methods = list(dict.fromkeys(str(row["method"]) for row in rows))
    figure = Figure(figsize=(14.0, 7.0), constrained_layout=True)
    axes = figure.subplots(1, 2)
    x = np.arange(len(scenarios), dtype=float)
    width = 0.18
    for method_index, method in enumerate(methods):
        selected = [row for row in rows if row["method"] == method]
        rmse = [float(row["rmse_hz"]) for row in selected]
        axes[0].bar(
            x + (method_index - 1.5) * width,
            rmse,
            width=width,
            color=METHOD_COLORS[method],
            label=method,
        )
    axes[0].set_yscale("log")
    axes[0].set_xticks(x, [item.replace(" ", "\n") for item in scenarios])
    axes[0].set_ylabel("CFO RMSE (Hz, log scale)")
    axes[0].set_title("A · Known-truth Monte Carlo", loc="left", fontweight="bold")
    axes[0].legend(fontsize=8)

    coverage_rows = [
        row for row in rows if row["method"] in {"parabolic-profile", "robust-profile"}
    ]
    for method_index, method in enumerate(("parabolic-profile", "robust-profile")):
        selected = [row for row in coverage_rows if row["method"] == method]
        coverage = [float(row["nominal_95_percent_coverage"]) for row in selected]
        axes[1].bar(
            x + (method_index - 0.5) * 0.34,
            coverage,
            width=0.34,
            color=METHOD_COLORS[method],
            label=method,
        )
    axes[1].axhline(0.95, color=RED, linestyle="--", linewidth=1.3, label="nominal 95%")
    axes[1].set_ylim(0, 1.04)
    axes[1].set_xticks(x, [item.replace(" ", "\n") for item in scenarios])
    axes[1].set_ylabel("reported ±1.96σ coverage")
    axes[1].set_title("B · Conditional uncertainty calibration", loc="left", fontweight="bold")
    axes[1].legend(fontsize=8)
    axes[1].text(
        0.02,
        0.08,
        (
            f"300 Hz mid-frame step: {step['detection_fraction']:.0%} detected at "
            f"{step['threshold_hz']:.0f} Hz split gate; "
            f"stationary false alarm {step['false_alarm_fraction']:.0%}."
        ),
        transform=axes[1].transAxes,
        fontsize=9,
        color=INK,
    )
    figure.suptitle(
        "Frame-CFO estimators: efficiency, contamination, and honest uncertainty",
        fontsize=16,
        fontweight="bold",
        color=INK,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def _plot_design(path: Path) -> None:
    figure = Figure(figsize=(14.0, 4.8), constrained_layout=True)
    axis = figure.subplots()
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    boxes = (
        (0.03, "Acquire timing +\nabsolute CFO alias", BLUE),
        (0.23, "Pilot wipeoff\n300 × 8 complex cube", GREEN),
        (0.43, "Ordinary profile +\nrobust challenger", AMBER),
        (0.63, "Fold/half/timing +\ntone-deletion audits", PURPLE),
        (0.83, "Qualified CFO +\nlikelihood/σ record", RED),
    )
    for x, text, color in boxes:
        axis.add_patch(
            matplotlib.patches.FancyBboxPatch(
                (x, 0.43),
                0.14,
                0.25,
                boxstyle="round,pad=0.02",
                facecolor=color,
                edgecolor="white",
                linewidth=1.5,
                alpha=0.95,
            )
        )
        axis.text(x + 0.07, 0.555, text, ha="center", va="center", color="white", fontsize=10)
    for x in (0.18, 0.38, 0.58, 0.78):
        axis.annotate(
            "",
            xy=(x + 0.04, 0.555),
            xytext=(x, 0.555),
            arrowprops={"arrowstyle": "->", "color": INK, "lw": 1.8},
        )
    axis.text(
        0.5,
        0.84,
        "Recommended fail-closed estimator path",
        ha="center",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )
    axis.text(
        0.5,
        0.19,
        (
            "The frame estimator refines one acquisition basin; it never chooses a "
            "227.273 kHz alias or a new timing lattice."
        ),
        ha="center",
        fontsize=11,
        color=INK,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180)


def _format(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _write_report(
    path: Path,
    *,
    evidence_path: Path,
    real_summary: dict[str, Any],
    synthetic: list[dict[str, Any]],
    step: dict[str, Any],
    real_figure: Path,
    synthetic_figure: Path,
    design_figure: Path,
    runtime: dict[str, Any] | None,
) -> None:
    parent = path.parent
    method_rows = "\n".join(
        "| {method} | {even_minus_odd_rms_hz:.1f} | {even_minus_odd_p95_absolute_hz:.1f} | "
        "{within_100_hz_fraction:.1%} | {eff} |".format(
            **row,
            eff=_format(row["median_heldout_likelihood_efficiency"], 3),
        )
        for row in real_summary["methods"]
    )
    synthetic_rows = "\n".join(
        f"| {row['scenario']} | {row['method']} | {row['bias_hz']:+.1f} | "
        f"{row['rmse_hz']:.1f} | {row['p95_absolute_error_hz']:.1f} | "
        f"{row['failure_over_100_hz_fraction']:.1%} | "
        f"{_format(row['nominal_95_percent_coverage'], 3)} |"
        for row in synthetic
    )
    split = real_summary["split_fold_disagreement"]
    uncertainty = real_summary["conditional_uncertainty_calibration"]
    subbin = real_summary["sub_bin_refinement"]
    timing = real_summary["timing_sensitivity"]
    robust = real_summary["robust_weighting"]
    tone = real_summary["tone_deletion_influence"]
    spur = step["coherent_one_tone_influence_test"]
    if runtime is None:
        runtime_text = "The bounded runtime benchmark has not been run on this host."
    else:
        point = runtime["ordinary_exact_profile_point_estimate"]
        qualified = runtime["qualified_public_api"]
        projection = runtime["median_projection"]
        p95_projection = runtime["p95_projection"]
        hardware = runtime["hardware"]
        runtime_text = (
            f"On `{hardware['cpu_model']}` with all listed BLAS thread pools pinned to one, "
            f"the exact-profile point fit took median {point['median_ms']:.3f} ms "
            f"(p95 {point['p95_ms']:.3f} ms), while the complete public API took median "
            f"{qualified['median_ms']:.3f} ms (p95 {qualified['p95_ms']:.3f} ms) over "
            f"{qualified['iteration_count']} iterations. A serial linear projection is "
            f"{projection['56_frames_75ms_segment_s']:.3f} s for 56 frames and "
            f"{projection['35000_frame_research_dwell_s']:.1f} s for 35,000 frames. "
            f"A deliberately conservative linear projection using the per-call p95 is "
            f"{p95_projection['56_frames_75ms_segment_s']:.3f} s and "
            f"{p95_projection['35000_frame_research_dwell_s']:.1f} s, respectively. "
            "Those are feasibility estimates, not production end-to-end timings; I/O, "
            "vectorized batching, CPU contention, and signal quality can change them."
        )
    text = f"""# Qualified CFO estimation in each 1.333 ms Qin pilot frame

## Bottom line

The existing tracked estimator is already a proper complex profile-likelihood
fit, not merely a line through wrapped phase. It removes one unknown complex
gain for each of the eight edge-pilot tones, searches a bounded residual CFO,
and locally refines the peak. The newer reset-debias prototype instead uses a
25 Hz discrete maximum on even Qin symbols and reserves odd symbols for
validation. The split is scientifically valuable, but the discrete point
estimate should receive a continuous sub-bin refinement and an explicit
fold-disagreement/uncertainty audit.

The recommended default point estimator is the **continuous ordinary
eight-gain profile maximum inside an acquisition-provided timing/CFO basin**.
The robust profile remains a research challenger and is not part of the public
point-estimator contract. An ordinary estimate is supported only when exact Qin
beats the rolled control, independent even/odd fold CFOs agree, the peak is not
on the search boundary, timing ±1 sample is stable, a half-frame test finds no
frequency step, and deleting any one pilot tone moves the CFO by at most 75 Hz.
This estimator cannot decide the ≈227.273 kHz OFDM alias; alias identity remains
an acquisition/replay responsibility.

![Recommended estimator path]({design_figure.relative_to(parent)})

## Two different meanings of “pilot”

This analysis uses the OFDM **edge pilots disclosed by Qin, Psiaki, Bowman, and
Humphreys**: 300 known 4QAM symbols on eight subcarriers at each edge of a
1.333 ms frame. See [*Pilots and Other Predictable Elements of the Starlink
Ku-Band Downlink*](https://arxiv.org/abs/2602.02627), especially its signal
model, edge-pilot section, and Appendix A sequences.

That is not the same observable as the older “pilot tones” in Kozhaya,
Saroufim, and Kassas: nine unmodulated, data-less tones in the silent center of
a Ku-band channel. [*Unveiling Starlink for
PNT*](https://doi.org/10.33012/navi.685) is therefore a methodological contrast,
not the source of our Qin sequence. Its pre-2024 OFDM examples report abrupt CFO
corrections on an approximately one-second grid; neither those center tones nor
that cadence should be conflated with the 50–100 ms stored-refill structure in
this corpus.

## What the current estimators compute

After exact Qin wipeoff, let `x[i,k]` be symbol `i`, tone `k`, and `t[i]` its
time. For trial residual frequency `f`, the ordinary estimator maximizes

```text
L(f) = Σ_k |Σ_i x[i,k] exp(-j 2π f t[i])|².
```

This is the Gaussian-noise maximum likelihood after analytically profiling out
eight nuisance gains `h[k]`. The current all-symbol implementation uses a
100 Hz coarse grid, 5 Hz fine grid, a parabolic peak, and two bounded
phase-slope refinements. The raw reset-debias prototype uses a 25 Hz argmax on
even symbols; odd symbols are independently maximized for validation.

The robust prototype starts from per-tone CFO consensus, then alternates the
profile maximum with Huber symbol weights and capped inverse-residual-variance
tone weights. This handles sparse bad Qin symbols and a minority of coherent
narrowband tone contaminants while retaining the ordinary ML solution under
clean Gaussian noise. A robust adjacent-symbol phase-difference estimator is
also tested as a search-free diagnostic; it is less efficient and should not
be the primary estimate.

## Real-IQ experiment

The test reran {real_summary["raw_frame_count"]} raw frames from
`cap-20260821T140820-470384cc9284`, `stream-0/RX0`, upper edge. Timing locks were
selected by the existing GLRT64/frozen-trajectory rule and stratified across
33.7–37.7 s. Of these, {real_summary["qualified_frame_count"]} passed the
declared even-Qin gate. Every method in the table uses even symbols; the odd
profile maximum is an independent comparison. The all-300-symbol current
estimate is excluded from this held-out comparison because it has seen the odd
symbols.

![Real-IQ estimator comparison]({real_figure.relative_to(parent)})

| even-trained method | even–odd RMS (Hz) | p95 | within 100 Hz | median odd-likelihood efficiency |
| --- | ---: | ---: | ---: | ---: |
{method_rows}

The ordinary phase-refined split CFO has median absolute even/odd disagreement
{split["median_absolute_hz"]:.1f} Hz and p95 {split["p95_absolute_hz"]:.1f} Hz;
{split["over_100_hz_fraction"]:.1%} exceed 100 Hz. That disagreement is a
direct per-frame quality observable and should be persisted, not hidden by
averaging the two folds.

### Sub-bin refinement

Parabolic interpolation moves the 25 Hz grid maximum by a median
{subbin["median_absolute_correction_hz"]:.2f} Hz (p95
{subbin["p95_absolute_correction_hz"]:.2f} Hz) and improves held-out odd
likelihood on {subbin["heldout_score_improved_fraction"]:.1%} of qualified
frames. A grid label is not an uncertainty statement: continuous refinement
removes deterministic quantization, but noise and model mismatch still govern
the error.

### Conditional uncertainty is not calibrated yet

Combining the current even/odd analytic sigmas predicts a median split sigma of
{uncertainty["median_predicted_split_sigma_hz"]:.1f} Hz, while empirical split
RMS is {uncertainty["empirical_split_rms_hz"]:.1f} Hz. Nominal 95% coverage is
{uncertainty["nominal_95_percent_coverage"]:.1%}, and standardized split RMS is
{uncertainty["standardized_difference_rms"]:.2f} rather than one. Until this is
calibrated by signal-quality strata, report both curvature/phase sigma and the
fold disagreement; use the larger for downstream weighting.

### Timing sensitivity

Moving the assumed frame epoch by one raw 2.5 MS/s sample changes the all-symbol
CFO by median {timing["minus_one_sample_median_absolute_hz"]:.1f} Hz for −1 and
{timing["plus_one_sample_median_absolute_hz"]:.1f} Hz for +1. The worst-direction
p95 is {timing["worst_shift_p95_absolute_hz"]:.1f} Hz and maximum is
{timing["worst_shift_maximum_absolute_hz"]:.1f} Hz. Therefore timing must be
bound to each source acquisition, and a ±1 sample sensitivity should be a
qualification field rather than silently reusing one epoch.

### Leave-one-tone-out influence

A single coherent contaminant can dominate the ordinary eight-tone sum while
exact/control, parity, and half-frame checks still agree. The auditable remedy
is not to replace Gaussian ML unconditionally: refit after deleting each of the
eight tones and record the maximum shift from the full fit. In the
`cap-...470384` real cohort the deletion spread is median {tone["median_spread_hz"]:.1f}
Hz, p95 {tone["p95_spread_hz"]:.1f} Hz, and maximum
{tone["maximum_spread_hz"]:.1f} Hz; none of {real_summary["qualified_frame_count"]}
coherence-qualified frames exceeds the 75 Hz gate. The independent T01/T06
checks likewise rejected 0/72 and 0/77,
with maxima 70.2 and 16.4 Hz. These three cohorts support 75 Hz as a
conservative first bound, not a universal population calibration.

### Robust weighting

The robust fit changes the ordinary even CFO by median
{robust["median_absolute_cfo_change_hz"]:.1f} Hz (p95
{robust["p95_absolute_cfo_change_hz"]:.1f} Hz) and improves independent odd
likelihood on {robust["heldout_score_improved_fraction"]:.1%} of qualified raw
frames. Its median heavy-downweight fraction is
{robust["median_heavily_downweighted_symbol_fraction"]:.1%}. Robust weighting
should therefore be promoted only with the held-out gain check: a changed CFO
is not automatically a better CFO.

### T01/T06 source-bound cross-check

A second raw-IQ check used eight stratified source-bound timing locks from each
of the ten-dwell cohort's T01 and T06 results. T01 is the reset-biased case
whose GLRT and local rates differ by 2.329 kHz/s; T06 is the falsification
control where the rates differ by only 0.003 kHz/s. The same eight-gain frame
gate retained 74/120 and 77/120 frames, respectively.

| dwell | grid RMS | parabolic | phase refine | robust | σ predicted / observed | 95% cover |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T01 | 43.38 Hz | 42.25 Hz | 42.22 Hz | 45.07 Hz | 42.13 / 42.22 Hz | 94.6% |
| T06 | 29.62 Hz | 29.47 Hz | 29.40 Hz | 28.23 Hz | 32.55 / 29.40 Hz | 97.4% |

Parabolic refinement improved held-out likelihood on 54.1% of T01 and 51.9%
of T06 frames. Robust weighting improved it on only 41.9% of T01 frames and
58.4% of T06 frames. This is the decisive reason not to make the robust fit an
unconditional replacement: contamination resistance is valuable, but clean
real frames retain the Gaussian-profile efficiency advantage. Frozen evidence
and input digests are recorded in
[`t01-t06-crosscheck.json`](figures/2026_08_24_frame_cfo_estimator_study/t01-t06-crosscheck.json).

The ±1-sample timing-spread p95 is 18.4 Hz for T01 and 17.0 Hz for T06;
neither cohort has a value above 50 Hz. A half-frame disagreement normalized by
the two half-fit sigmas exceeds 4 only once in 72 T01 frames and never in 77
T06 frames. These results support 50 Hz timing and 4σ half-frame gates as
conservative first defaults, with continued monitoring rather than claims of
universal calibration.

## Known-truth simulation

The Monte Carlo randomizes eight complex channel gains and true residual CFO.
It covers clean high/medium/low SNR, 15% symbol contamination, and one coherent
tone spur. It is an estimator stress test, not a radio-fidelity claim.

![Synthetic estimator benchmark]({synthetic_figure.relative_to(parent)})

| scenario | method | bias (Hz) | RMSE (Hz) | p95 abs (Hz) | >100 Hz | nominal 95% coverage |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{synthetic_rows}

The ordinary estimator fails by more than 100 Hz in
{spur["ordinary_failure_over_100_hz_count"]}/{spur["trial_count"]} coherent
one-tone trials. Exact/control, parity, half-frame,
timing-stability-by-construction, and boundary gates still falsely accept
{spur["baseline_gate_false_accept_count"]} of those failures. The 75 Hz
leave-one-tone-out gate catches
{spur["ordinary_failures_caught_count"]}/{spur["ordinary_failure_over_100_hz_count"]}
ordinary failures and all
{spur["baseline_false_accepts_caught_count"]}/{spur["baseline_gate_false_accept_count"]}
otherwise-false accepts; the smallest deletion spread among the failed trials is
{spur["minimum_failure_tone_deletion_spread_hz"]:.1f} Hz. This exact 40-trial
regression is component-tested.

A separate {step["injected_step_hz"]:.0f} Hz mid-frame step is detected by a
{step["threshold_hz"]:.0f} Hz half-frame disagreement gate in
{step["detection_fraction"]:.1%} of trials, with
{step["false_alarm_fraction"]:.1%} false alarms on stationary controls. Such a
frame violates the constant-CFO measurement model and should be rejected or
split; forcing one CFO through it can manufacture a biased ramp point.

## Recommended estimator and gates

1. Bind every frame to the exact source timing epoch and raw CFO alias selected
   by GLRT/replay. Search only a declared residual interval such as ±2 or ±6
   kHz. Never modulo-canonicalize an absolute CFO before raw-IQ correction.
2. Demodulate all 300 Qin symbols into an `N×8` complex pilot-wiped cube. Keep
   one complex nuisance gain per tone.
3. Compute a continuous ordinary profile peak. The implemented public kernel
   uses its existing 100 Hz coarse grid, 5 Hz local grid, parabolic peak, and
   two bounded phase refinements. Retain the boundary flag, conditional sigma,
   exact score, and independently maximized rolled-control score.
4. Fit the even and odd interleaved Qin folds independently. Reject when their
   CFOs differ by more than 100 Hz. This preserves the full 1.32 ms aperture in
   both folds and is already calibrated on three real-data cohorts.
5. Recompute at timing −1/0/+1 sample and reject when the maximum CFO spread
   exceeds 50 Hz.
6. Compare first-half and second-half CFO. Reject when their difference exceeds
   four times the combined conditional sigma; this catches a reset inside a
   frame without penalizing weak halves solely for a fixed-Hz difference.
7. Delete each pilot tone in turn. Reject when any deletion moves the full CFO
   by more than 75 Hz; persist that maximum as `tone_deletion_spread_hz`.
8. Keep robust weighting as a shadow diagnostic. It may be promoted later with
   a separately validated contamination trigger; current real data do not
   justify placing its weights or alternate CFO in the public contract.
9. For a 50–125 ms Doppler ramp, prefer the sum of per-frame profile
   likelihoods under one ramp slope and free ramp intercept over unweighted
   regression of point maxima. This propagates weak-frame information without
   letting maximized noise cells vote equally.

### Public API and result fields

The implemented narrow analysis API is:

```text
estimate_edge_pilot_frame_cfo(
    samples, sample_rate_hz,
    *, frame_start_sample, acquisition_absolute_cfo_hz, edge, config
) -> PilotFrameCfoEstimate
```

`samples` is exactly one compact guarded frame slice: one sample before the
nominal frame, complete frame content, and one sample after it.
`frame_start_sample` is the nominal frame's **absolute recording coordinate**,
not an index into the compact slice. This distinction is component-tested at a
large nonzero recording coordinate.

The implemented `PilotFrameCfoConfig` contains `residual_half_width_hz`,
`minimum_exact_coherence=0.02`, `minimum_coherence_margin=0`,
`maximum_even_odd_disagreement_hz=100`,
`maximum_timing_spread_hz=50`, `maximum_half_frame_z=4`, and
`maximum_tone_deletion_shift_hz=75`. Search-grid and continuous-refinement
details are fixed by the implementation rather than exposed as tuning knobs.

`PilotFrameCfoEstimate` contains:

- `status`, `measurement_supported`, and controlled `rejection_reasons`;
- `frame_start_sample` and `reference_sample`;
- selected `absolute_cfo_hz`, `residual_cfo_hz`, and
  `frequency_uncertainty_hz`;
- `exact_coherence`, `control_coherence`, and `coherence_margin`;
- `even_residual_cfo_hz`, `odd_residual_cfo_hz`, and
  `even_odd_disagreement_hz`;
- `timing_spread_hz`, `half_frame_difference_z`,
  `tone_deletion_spread_hz`, and `search_boundary`.

The API refines one already selected basin. It must not accept or return a
modulo-canonical CFO alias, choose a different timing lattice, or connect phase
between frames.

## Impact on Doppler-rate estimation

Independent frame error `σ_f` gives an ideal equally spaced slope uncertainty
approximately `sqrt(12/N) σ_f / T`, where `N` frames span `T`. At 750 Hz, a
75 ms segment has about 56 frames; 25 Hz frame error alone corresponds to
roughly 154 Hz/s ideal slope uncertainty. Correlated timing errors, within-frame
steps, selection on the maximizing CFO cell, and source-time errors do not
average this way. They can bias a slope by kHz/s.

The latest independent timing evidence identifies **stored refill-time
compression** as the dominant cause of this corpus's sawtooth: samples within a
stored refill retain a useful local clock, but elapsed RF time omitted between
refills is not represented by a naive contiguous sample index. An accurate
frame CFO therefore measures the carrier rate *within each stored refill*; it
cannot reconstruct omitted elapsed RF time. A Doppler ramp must preserve refill
boundaries and restore or independently validate the physical time coordinate
before joining them. See
[`2026_08_24_refill_time_compression_sawtooth.md`](2026_08_24_refill_time_compression_sawtooth.md).
This supersedes treating a transmitter-state change as the primary explanation
here. Even after time repair, satellite-only interpretation still requires
receiver-clock calibration and orbit/common-mode tests.

## Bounded runtime benchmark

{runtime_text}

## Reproducibility

Machine-readable evidence: [{evidence_path.name}]({evidence_path.relative_to(parent)}).

```bash
PYTHONPATH=src python tools/report_frame_cfo_estimator_study.py
taskset -c 0 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONPATH=src \
python tools/benchmark_pilot_frame_cfo.py
```

No RF was collected. The QNAP corpus and sealed Standard products were opened
read-only.
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = _arguments()
    raw, provenance = _raw_comparisons(
        bulk_root=args.bulk_root,
        analysis_root=args.analysis_root,
        maximum_windows=args.maximum_windows,
    )
    real_summary = _summary(raw)
    synthetic, step = _synthetic_benchmark(args.synthetic_replicates)
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)
    real_figure = output / "real-iq-frame-cfo-comparison.png"
    synthetic_figure = output / "synthetic-frame-cfo-benchmark.png"
    design_figure = output / "recommended-frame-cfo-estimator.png"
    evidence_path = output / "frame-cfo-estimator-evidence.json"
    runtime_path = output / "frame-cfo-runtime-benchmark.json"
    runtime = _load(runtime_path) if runtime_path.exists() else None
    _plot_real(raw, real_figure)
    _plot_synthetic(synthetic, step, synthetic_figure)
    _plot_design(design_figure)
    document = {
        "schema": "org.leo.research.frame-cfo-estimator-study/v1",
        "algorithm": "eight-gain-profile-qualified-frame-cfo-audit-v2",
        "provenance": provenance,
        "configuration": {
            "maximum_windows": args.maximum_windows,
            "synthetic_replicates_per_scenario": args.synthetic_replicates,
            "residual_search_half_width_hz": 2_000.0,
            "discrete_grid_step_hz": 25.0,
            "timing_sensitivity_samples": [-1, 0, 1],
            "maximum_even_odd_disagreement_hz": 100.0,
            "maximum_timing_spread_hz": 50.0,
            "maximum_half_frame_z": 4.0,
            "maximum_tone_deletion_shift_hz": 75.0,
        },
        "real_summary": real_summary,
        "synthetic_summary": synthetic,
        "within_frame_step_test": step,
        "raw_frames": [asdict(item) | {"qualified": item.qualified} for item in raw],
        "figures": {},
        "candidate_only": True,
        "known_pilots_only": True,
        "payload_decoded": False,
        "runtime_benchmark": (
            None
            if runtime is None
            else {
                "path": str(runtime_path),
                "sha256": _sha256(runtime_path),
                "schema": runtime.get("schema"),
            }
        ),
    }
    for path in (real_figure, synthetic_figure, design_figure):
        document["figures"][path.name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
    evidence_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_report(
        args.report_path,
        evidence_path=evidence_path,
        real_summary=real_summary,
        synthetic=synthetic,
        step=step,
        real_figure=real_figure,
        synthetic_figure=synthetic_figure,
        design_figure=design_figure,
        runtime=runtime,
    )
    print(
        f"wrote {evidence_path} and {args.report_path} from {len(raw)} raw frames",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
