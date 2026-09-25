#!/usr/bin/env python3
"""Compare equal, PSS-quality-weighted, and quality-plus-Huber PSS fits."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from leo.contracts.standard_native_pss import (  # noqa: E402
    StandardNativePssFrameTimingV1,
)
from matplotlib import pyplot as plt  # noqa: E402

SESSION_ID = "cap-20260903T004006-9120aba2922e"
RF_REFERENCE_HZ = 11_217_500_000.0
HERE = Path(__file__).resolve().parent
WINDOW_ROOT = HERE.parent / "2026_09_03_9120_pss_window_sensitivity"
PRODUCTS = {
    "half": WINDOW_ROOT / "pss-half-62.5ms-31.25ms.json",
    "baseline": Path(
        "/srv/bulk/leo/analysis/cap-20260903T004006-9120aba2922e/"
        "native-capture-e77330d77f904d928137be403995a77f/scientific/"
        "path-pss-native/"
        "sha256:206dad357c678770b9f1b5257f0dad385aecff9348ec08198f258bdf5c398c80/"
        "standard.pss-frame-timing.v1.json"
    ),
    "double": WINDOW_ROOT / "pss-double-250ms-125ms.json",
}
LABELS = {
    "half": "62.5/31.25 ms",
    "baseline": "125/62.5 ms",
    "double": "250/125 ms",
}
METHODS = ("equal", "quality_wls", "quality_huber")
METHOD_LABELS = {
    "equal": "Equal weight",
    "quality_wls": "Robust-z WLS",
    "quality_huber": "Robust-z WLS + Huber",
}
COLORS = {
    "equal": "#374151",
    "quality_wls": "#f97316",
    "quality_huber": "#7c3aed",
}


@dataclass(frozen=True)
class TrackData:
    times_s: np.ndarray
    phases_s: np.ndarray
    robust_z: np.ndarray


@dataclass(frozen=True)
class Fit:
    method: str
    origin_s: float
    coefficients_s: np.ndarray
    residuals_us: np.ndarray
    weights: np.ndarray
    iterations: int

    @property
    def rate_khz_per_s(self) -> float:
        return -RF_REFERENCE_HZ * 2.0 * self.coefficients_s[0] / 1e3

    @property
    def unweighted_rms_us(self) -> float:
        return float(np.sqrt(np.mean(self.residuals_us**2)))

    @property
    def weighted_rms_us(self) -> float:
        return float(np.sqrt(np.average(self.residuals_us**2, weights=self.weights)))

    @property
    def maximum_absolute_residual_us(self) -> float:
        return float(np.max(np.abs(self.residuals_us)))

    @property
    def effective_sample_count(self) -> float:
        return float(self.weights.sum() ** 2 / np.dot(self.weights, self.weights))


def load_track(path: Path) -> TrackData:
    product = StandardNativePssFrameTimingV1.model_validate_json(path.read_bytes())
    track = max(
        product.tracks,
        key=lambda item: (
            len(item.mode_ids),
            item.time_stop_s - item.time_start_s,
            -item.rms_residual_us,
            item.track_id,
        ),
    )
    modes_by_id = {item.mode_id: item for item in product.modes}
    modes = [modes_by_id[item] for item in track.mode_ids]
    times = np.asarray([item.center_time_s for item in modes], dtype=float)
    phases = np.polyval(
        np.asarray(track.coefficients_descending_s, dtype=float),
        times - track.time_origin_s,
    ) + np.asarray(track.residuals_us, dtype=float) / 1e6
    return TrackData(
        times_s=times,
        phases_s=phases,
        robust_z=np.asarray([item.robust_z for item in modes], dtype=float),
    )


def quality_weights(robust_z: np.ndarray) -> np.ndarray:
    """Use robust-z as a bounded relative inverse-variance proxy."""

    weights = np.clip(robust_z / np.median(robust_z), 0.5, 2.0)
    return weights / np.mean(weights)


def polynomial_fit(
    times: np.ndarray,
    phases: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, np.ndarray]:
    origin = float(np.mean(times))
    coefficients = np.polyfit(
        times - origin,
        phases,
        2,
        w=np.sqrt(weights),
    )
    return origin, coefficients


def fit_track(data: TrackData, method: str) -> Fit:
    if method not in METHODS:
        raise ValueError(f"unknown fit method: {method}")
    base = (
        np.ones(data.times_s.size, dtype=float)
        if method == "equal"
        else quality_weights(data.robust_z)
    )
    weights = base.copy()
    iterations = 1
    if method == "quality_huber":
        for iteration in range(1, 31):
            iterations = iteration
            origin, coefficients = polynomial_fit(data.times_s, data.phases_s, weights)
            residuals = data.phases_s - np.polyval(coefficients, data.times_s - origin)
            scale = 1.4826 * np.median(np.abs(residuals - np.median(residuals)))
            huber = np.minimum(
                1.0,
                1.345 * scale / np.maximum(np.abs(residuals), 1e-30),
            )
            updated = base * huber
            if float(np.max(np.abs(updated - weights))) < 1e-10:
                weights = updated
                break
            weights = updated
    origin, coefficients = polynomial_fit(data.times_s, data.phases_s, weights)
    residuals_us = (
        data.phases_s - np.polyval(coefficients, data.times_s - origin)
    ) * 1e6
    return Fit(
        method=method,
        origin_s=origin,
        coefficients_s=coefficients,
        residuals_us=residuals_us,
        weights=weights,
        iterations=iterations,
    )


def parity_rates(data: TrackData, method: str) -> list[float]:
    rates = []
    for parity in (0, 1):
        indexes = np.arange(parity, data.times_s.size, 2)
        subset = TrackData(
            times_s=data.times_s[indexes],
            phases_s=data.phases_s[indexes],
            robust_z=data.robust_z[indexes],
        )
        rates.append(fit_track(subset, method).rate_khz_per_s)
    return rates


def fit_prediction(fit: Fit, times: np.ndarray) -> np.ndarray:
    return np.polyval(fit.coefficients_s, times - fit.origin_s)


def frequency_change_hz(fit: Fit, times: np.ndarray, reference_s: float) -> np.ndarray:
    local = times - fit.origin_s
    reference_local = reference_s - fit.origin_s
    drift = 2.0 * fit.coefficients_s[0] * local + fit.coefficients_s[1]
    reference_drift = (
        2.0 * fit.coefficients_s[0] * reference_local + fit.coefficients_s[1]
    )
    return -RF_REFERENCE_HZ * (drift - reference_drift)


def result_row(resolution: str, data: TrackData, fit: Fit, equal: Fit) -> dict[str, object]:
    parities = parity_rates(data, fit.method)
    prediction_shift_ns = (
        fit_prediction(fit, data.times_s) - fit_prediction(equal, data.times_s)
    ) * 1e9
    return {
        "resolution": resolution,
        "window_stride": LABELS[resolution],
        "method": fit.method,
        "method_label": METHOD_LABELS[fit.method],
        "point_count": int(data.times_s.size),
        "rate_khz_per_s": fit.rate_khz_per_s,
        "rate_delta_from_equal_hz_per_s": (fit.rate_khz_per_s - equal.rate_khz_per_s) * 1e3,
        "unweighted_rms_us": fit.unweighted_rms_us,
        "weighted_rms_us": fit.weighted_rms_us,
        "maximum_absolute_residual_us": fit.maximum_absolute_residual_us,
        "effective_sample_count": fit.effective_sample_count,
        "minimum_weight": float(np.min(fit.weights)),
        "median_weight": float(np.median(fit.weights)),
        "maximum_weight": float(np.max(fit.weights)),
        "points_below_half_weight": int(np.count_nonzero(fit.weights < 0.5)),
        "maximum_fit_shift_ns": float(np.max(np.abs(prediction_shift_ns))),
        "robust_z_vs_absolute_equal_residual_correlation": float(
            np.corrcoef(data.robust_z, np.abs(equal.residuals_us))[0, 1]
        ),
        "nonoverlap_parity_rates_khz_per_s": parities,
        "nonoverlap_parity_rate_spread_hz_per_s": abs(parities[0] - parities[1]) * 1e3,
        "iterations": fit.iterations,
    }


def render(
    data_by_resolution: dict[str, TrackData],
    fits_by_resolution: dict[str, dict[str, Fit]],
) -> None:
    figure, axes = plt.subplots(
        3,
        2,
        figsize=(16, 13),
        constrained_layout=True,
        sharex="col",
    )
    for row_index, resolution in enumerate(("half", "baseline", "double")):
        data = data_by_resolution[resolution]
        fits = fits_by_resolution[resolution]
        equal = fits["equal"]
        left, right = axes[row_index]
        left.grid(True, alpha=0.22)
        right.grid(True, alpha=0.22)
        left.axhline(0.0, color="#111827", linewidth=0.8)
        right.axhline(0.0, color="#111827", linewidth=0.8)
        normalized = quality_weights(data.robust_z)
        sizes = 8.0 + 18.0 * (normalized - normalized.min()) / (
            normalized.max() - normalized.min()
        )
        equal_residual = (
            data.phases_s - fit_prediction(equal, data.times_s)
        ) * 1e6
        left.scatter(
            data.times_s,
            equal_residual,
            s=sizes,
            color="#64748b",
            alpha=0.48,
            label="Observed residual; marker size = robust-z weight",
        )
        for method in ("quality_wls", "quality_huber"):
            correction = (
                fit_prediction(fits[method], data.times_s)
                - fit_prediction(equal, data.times_s)
            ) * 1e6
            left.plot(
                data.times_s,
                correction,
                color=COLORS[method],
                linewidth=2.0,
                label=f"{METHOD_LABELS[method]} fit shift",
            )
        reference = float(np.mean(data.times_s))
        equal_frequency = frequency_change_hz(equal, data.times_s, reference)
        for method in ("quality_wls", "quality_huber"):
            fit = fits[method]
            delta = frequency_change_hz(fit, data.times_s, reference) - equal_frequency
            right.plot(
                data.times_s,
                delta,
                color=COLORS[method],
                linewidth=2.0,
                label=(
                    f"{METHOD_LABELS[method]}: {fit.rate_khz_per_s:.6f} kHz/s "
                    f"({(fit.rate_khz_per_s - equal.rate_khz_per_s) * 1e3:+.2f} Hz/s)"
                ),
            )
        left.set_ylabel(f"{LABELS[resolution]}\nTiming residual / fit shift (µs)")
        right.set_ylabel("Weighted − equal frequency change (Hz)")
        left.legend(loc="best", fontsize=7)
        right.legend(
            title=f"Equal: {equal.rate_khz_per_s:.6f} kHz/s",
            loc="best",
            fontsize=7,
            title_fontsize=7,
        )
    axes[0, 0].set_title("A · Timing observations and movement of the fitted curve")
    axes[0, 1].set_title("B · Magnified frequency-change difference from equal weighting")
    axes[-1, 0].set_xlabel("Device-axis seconds from recording start")
    axes[-1, 1].set_xlabel("Device-axis seconds from recording start")
    figure.suptitle(
        f"{SESSION_ID} · effect of PSS-quality weighting at all three resolutions\n"
        "quality q = clip(robust-z / median robust-z, 0.5, 2); "
        "WLS minimizes Σ q·residual²"
    )
    figure.savefig(HERE / "weighted-fit-comparison.png", dpi=170)
    plt.close(figure)


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    data_by_resolution = {name: load_track(path) for name, path in PRODUCTS.items()}
    fits_by_resolution = {
        name: {method: fit_track(data, method) for method in METHODS}
        for name, data in data_by_resolution.items()
    }
    rows = [
        result_row(
            resolution,
            data_by_resolution[resolution],
            fits_by_resolution[resolution][method],
            fits_by_resolution[resolution]["equal"],
        )
        for resolution in ("half", "baseline", "double")
        for method in METHODS
    ]
    method_summaries = {}
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        rates = [float(row["rate_khz_per_s"]) for row in selected]
        method_summaries[method] = {
            "cross_resolution_rate_range_hz_per_s": (max(rates) - min(rates)) * 1e3,
            "rates_khz_per_s": rates,
        }
    result = {
        "session_id": SESSION_ID,
        "rf_reference_hz": RF_REFERENCE_HZ,
        "quality_weight_formula": "q=clip(robust_z/median(robust_z),0.5,2), normalized to mean 1",
        "wls_objective": "sum(q_i * residual_i**2); numpy.polyfit receives sqrt(q_i)",
        "huber_formula": "q_total=q*min(1,1.345*MAD_scale/abs(residual)); iterated to convergence",
        "rows": rows,
        "method_summaries": method_summaries,
    }
    (HERE / "weighted-fit-comparison.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (HERE / "weighted-fit-comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render(data_by_resolution, fits_by_resolution)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
