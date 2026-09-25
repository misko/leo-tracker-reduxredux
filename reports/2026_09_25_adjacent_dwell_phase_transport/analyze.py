from __future__ import annotations

import importlib.util
import json
import math
from functools import lru_cache
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = REPORT_DIR.parent / "2026_09_25_single_track_cross_dwell_phase"
SOURCE_RESULTS = SOURCE_DIR / "results.json"
SOURCE_ANALYSIS = SOURCE_DIR / "analyze.py"
VISITS = (766, 767)
CONSECUTIVE_SHARED_PAIRS = (
    (637, 638),
    (654, 655),
    (687, 688),
    (688, 689),
    (689, 690),
    (700, 701),
    (705, 706),
    (706, 707),
    (707, 708),
    (766, 767),
    (775, 776),
)
SEED_HZ = 674_853.3580860491
PRIMARY_WINDOW = 4096
PRIMARY_DEGREE = 2
BOOTSTRAP_SEED = 20_260_925
BOOTSTRAP_COUNT = 2_000
UNIFORM_NULL_TRIALS = 2_000_000


@lru_cache(maxsize=1)
def source_module():
    spec = importlib.util.spec_from_file_location("single_track_phase_source", SOURCE_ANALYSIS)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load source analysis")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wrap_rad(value: np.ndarray | float) -> np.ndarray:
    return (np.asarray(value) + np.pi) % (2 * np.pi) - np.pi


def circular_r(phase: np.ndarray, weight: np.ndarray) -> float:
    return float(abs(np.sum(weight * np.exp(1j * phase))) / np.sum(weight))


def uniform_resultant_null_p(
    sample_count: int, observed_r: float, seed: int, trials: int = UNIFORM_NULL_TRIALS
) -> tuple[float, int]:
    """Monte Carlo tail probability for a circular resultant under uniform phase."""
    rng = np.random.default_rng(seed)
    exceedances = 0
    batch_size = 100_000
    completed = 0
    while completed < trials:
        count = min(batch_size, trials - completed)
        phase = rng.uniform(-np.pi, np.pi, (count, sample_count))
        resultant = abs(np.mean(np.exp(1j * phase), axis=1))
        exceedances += int(np.sum(resultant >= observed_r))
        completed += count
    return (exceedances + 1) / (trials + 1), exceedances


def pair_phasors(
    document: dict, window: int, visits: tuple[int, int] = VISITS
) -> dict:
    module = source_module()
    sample_rate = module.SAMPLE_RATE_HZ
    track_points = {
        row["visit_index"]: row for row in document["track_points"]["rx0"]
    }
    reference_counter = min(row["valid_start_counter"] for row in track_points.values())
    times, phasors, coherence, labels = [], [], [], []
    taper = np.hanning(window) ** 2
    for visit_index in visits:
        iq, _ = module.load_visit(visit_index)
        starts = np.arange(0, len(iq) - window + 1, window // 2)
        for start in starts:
            samples = np.arange(start, start + window)
            global_time = (
                track_points[visit_index]["valid_start_counter"]
                - reference_counter
                + samples
            ) / sample_rate
            left = iq[start : start + window, 0].astype(np.complex128)
            right = iq[start : start + window, 1].astype(np.complex128)
            right *= np.exp(-2j * np.pi * SEED_HZ * global_time)
            phasor = np.sum(np.conj(left) * right * taper)
            denominator = math.sqrt(
                max(
                    float(
                        np.sum(abs(left * np.sqrt(taper)) ** 2)
                        * np.sum(abs(right * np.sqrt(taper)) ** 2)
                    ),
                    1e-30,
                )
            )
            times.append(
                (
                    track_points[visit_index]["valid_start_counter"]
                    - reference_counter
                    + start
                    + (window - 1) / 2
                )
                / sample_rate
            )
            phasors.append(phasor)
            coherence.append(abs(phasor) / denominator)
            labels.append(visit_index)
    return {
        "time_s": np.asarray(times),
        "phasor": np.asarray(phasors),
        "coherence": np.asarray(coherence),
        "visit_index": np.asarray(labels),
    }


def fit_increment_model(
    series: dict,
    degree: int,
    train_indices: np.ndarray | None = None,
    fit_radius_s: float | None = None,
) -> dict:
    time_s = series["time_s"]
    phasor = series["phasor"]
    labels = series["visit_index"]
    delta_time = np.diff(time_s)
    midpoint = (time_s[1:] + time_s[:-1]) / 2
    delta_phase = np.angle(phasor[1:] * np.conj(phasor[:-1]))
    same_dwell = labels[1:] == labels[:-1]
    boundary_index = int(np.flatnonzero(~same_dwell)[0])
    center_s = float(np.mean(midpoint))
    centered_midpoint = midpoint - center_s
    frequency_hz = delta_phase / (2 * np.pi * delta_time)
    weight = np.sqrt(abs(phasor[1:] * phasor[:-1]))
    design = np.column_stack(
        [centered_midpoint**power for power in range(degree + 1)]
    )
    available_mask = same_dwell.copy()
    if fit_radius_s is not None:
        boundary_time = (time_s[boundary_index] + time_s[boundary_index + 1]) / 2
        available_mask &= abs(midpoint - boundary_time) <= fit_radius_s
    available = np.flatnonzero(available_mask)
    selected = available if train_indices is None else np.asarray(train_indices)
    coefficients = np.linalg.lstsq(
        design[selected] * weight[selected, None],
        frequency_hz[selected] * weight[selected],
        rcond=None,
    )[0]

    def integral(at_time: np.ndarray) -> np.ndarray:
        centered = np.asarray(at_time) - center_s
        return sum(
            coefficients[power] * centered ** (power + 1) / (power + 1)
            for power in range(degree + 1)
        )

    predicted_boundary_cycles = float(
        integral(time_s[boundary_index + 1]) - integral(time_s[boundary_index])
    )
    boundary_residual_rad = float(
        wrap_rad(delta_phase[boundary_index] - 2 * np.pi * predicted_boundary_cycles)
    )
    corrected_phase = wrap_rad(np.angle(phasor) - 2 * np.pi * integral(time_s))
    residual_increment = wrap_rad(
        delta_phase - 2 * np.pi * (integral(time_s[1:]) - integral(time_s[:-1]))
    )
    return {
        "degree": degree,
        "center_s": center_s,
        "coefficients": coefficients,
        "boundary_index": boundary_index,
        "boundary_residual_deg": math.degrees(boundary_residual_rad),
        "corrected_phase_rad": corrected_phase,
        "residual_increment_rad": residual_increment,
        "same_dwell": same_dwell,
        "available_indices": available,
        "frequency_hz_at_center": SEED_HZ + float(coefficients[0]),
    }


def analyze() -> dict:
    document = json.loads(SOURCE_RESULTS.read_text())
    rows = {row["visit_index"]: row for row in document["rows"]}
    primary_series = pair_phasors(document, PRIMARY_WINDOW)
    primary_fit = fit_increment_model(primary_series, PRIMARY_DEGREE)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    bootstrap = []
    available = primary_fit["available_indices"]
    for _ in range(BOOTSTRAP_COUNT):
        selected = np.sort(rng.choice(available, len(available) // 2, replace=False))
        fitted = fit_increment_model(primary_series, PRIMARY_DEGREE, selected)
        bootstrap.append(fitted["boundary_residual_deg"])
    bootstrap_array = np.asarray(bootstrap)

    window_sensitivity = []
    for window in (2048, 4096, 8192, 16384, 32768):
        series = pair_phasors(document, window)
        fitted = fit_increment_model(series, PRIMARY_DEGREE)
        window_sensitivity.append(
            {
                "window_samples": window,
                "window_us": window / 10.0,
                "boundary_residual_deg": fitted["boundary_residual_deg"],
            }
        )
    degree_sensitivity = []
    for degree in range(4):
        fitted = fit_increment_model(primary_series, degree)
        degree_sensitivity.append(
            {
                "frequency_polynomial_degree": degree,
                "boundary_residual_deg": fitted["boundary_residual_deg"],
            }
        )
    geometry = document["expected_satellite_phase"]
    row_indices = {row["visit_index"]: index for index, row in enumerate(document["rows"])}
    left_index, right_index = (row_indices[visit] for visit in VISITS)
    expected_center_changes = {
        label: values[right_index] - values[left_index]
        for label, values in geometry["orientation_phase_change_deg"].items()
    }
    labels = primary_series["visit_index"]
    boundary_index = int(np.flatnonzero(labels[1:] != labels[:-1])[0])
    boundary_times = primary_series["time_s"][
        [boundary_index, boundary_index + 1]
    ]
    boundary_geometry = source_module().expected_satellite_phase(
        [
            {"track_time_s": float(boundary_times[0])},
            {"track_time_s": float(np.mean(boundary_times))},
            {"track_time_s": float(boundary_times[1])},
        ],
        document["track_points"],
    )
    east_west_label = "east–west (az 90°)"
    boundary_east_west_change = boundary_geometry[
        "orientation_phase_change_deg"
    ][east_west_label][-1]
    track_rows = {row["visit_index"]: row for row in document["rows"]}
    track_points = {
        row["visit_index"]: row for row in document["track_points"]["rx0"]
    }
    validation_pairs = []
    for pair in CONSECUTIVE_SHARED_PAIRS:
        series = pair_phasors(document, PRIMARY_WINDOW, pair)
        fitted = fit_increment_model(series, PRIMARY_DEGREE)
        pair_labels = series["visit_index"]
        pair_boundary = int(np.flatnonzero(pair_labels[1:] != pair_labels[:-1])[0])
        boundary_dt_s = float(
            series["time_s"][pair_boundary + 1] - series["time_s"][pair_boundary]
        )
        center_dt_s = float(
            track_rows[pair[1]]["track_time_s"] - track_rows[pair[0]]["track_time_s"]
        )
        center_east_west_deg = float(
            geometry["orientation_phase_change_deg"][east_west_label][
                row_indices[pair[1]]
            ]
            - geometry["orientation_phase_change_deg"][east_west_label][
                row_indices[pair[0]]
            ]
        )
        validation_pairs.append(
            {
                "visits": list(pair),
                "held_boundary_residual_deg": fitted["boundary_residual_deg"],
                "seed_only_boundary_change_deg": float(
                    np.degrees(
                        np.angle(
                            series["phasor"][pair_boundary + 1]
                            * np.conj(series["phasor"][pair_boundary])
                        )
                    )
                ),
                "boundary_window_center_separation_us": boundary_dt_s * 1e6,
                "expected_east_west_boundary_change_deg": (
                    center_east_west_deg * boundary_dt_s / center_dt_s
                ),
                "expected_east_west_center_change_deg": center_east_west_deg,
                "minimum_boundary_window_coherence": float(
                    min(
                        series["coherence"][pair_boundary],
                        series["coherence"][pair_boundary + 1],
                    )
                ),
                "minimum_whole_dwell_resultant": float(
                    min(
                        track_rows[pair[0]]["phase_resultant"],
                        track_rows[pair[1]]["phase_resultant"],
                    )
                ),
                "minimum_median_direct_coherence": float(
                    min(
                        track_rows[pair[0]]["median_coherence"],
                        track_rows[pair[1]]["median_coherence"],
                    )
                ),
                "valid_payload_gap_us": float(
                    (
                        track_points[pair[1]]["valid_start_counter"]
                        - track_points[pair[0]]["valid_start_counter"]
                        - 1_200_000
                    )
                    / 10.0
                ),
            }
        )
    validation_residual = np.asarray(
        [row["held_boundary_residual_deg"] for row in validation_pairs]
    )
    seed_only_change = np.radians(
        [row["seed_only_boundary_change_deg"] for row in validation_pairs]
    )
    validation_phase = np.radians(validation_residual)
    validation_r = circular_r(validation_phase, np.ones_like(validation_phase))
    validation_mean_deg = float(
        np.degrees(np.angle(np.mean(np.exp(1j * validation_phase))))
    )
    validation_null_p, validation_null_exceedances = uniform_resultant_null_p(
        len(validation_phase), validation_r, BOOTSTRAP_SEED + 1
    )
    discovery_index = CONSECUTIVE_SHARED_PAIRS.index(VISITS)
    confirmation_phase = np.delete(validation_phase, discovery_index)
    confirmation_r = circular_r(confirmation_phase, np.ones_like(confirmation_phase))
    confirmation_null_p, confirmation_null_exceedances = uniform_resultant_null_p(
        len(confirmation_phase), confirmation_r, BOOTSTRAP_SEED + 2
    )
    result = {
        "schema_version": 1,
        "session_id": document["session_id"],
        "track_ids": document["track_ids"],
        "visits": list(VISITS),
        "selection_status": (
            "exploratory high-signal consecutive pair; selected after phase inspection"
        ),
        "same_channel": True,
        "same_fastlock_profile": True,
        "relative_timing_delay_samples": 0,
        "complex_channel_response_used": False,
        "per_dwell_phase_intercepts_fitted": False,
        "global_phase_intercept_used": False,
        "carrier_seed_hz": SEED_HZ,
        "primary_window_samples": PRIMARY_WINDOW,
        "primary_stride_samples": PRIMARY_WINDOW // 2,
        "primary_frequency_polynomial_degree": PRIMARY_DEGREE,
        "fit_uses_boundary_increment": False,
        "fit_uses_random_points_across_both_whole_dwells": True,
        "visit_quality": {
            str(visit): {
                "whole_dwell_phase_resultant": rows[visit]["phase_resultant"],
                "median_direct_coherence": rows[visit]["median_coherence"],
            }
            for visit in VISITS
        },
        "boundary": {
            "gap_between_valid_payloads_us": (
                document["track_points"]["rx0"][
                    next(
                        index
                        for index, point in enumerate(document["track_points"]["rx0"])
                        if point["visit_index"] == VISITS[1]
                    )
                ]["valid_start_counter"]
                - document["track_points"]["rx0"][
                    next(
                        index
                        for index, point in enumerate(document["track_points"]["rx0"])
                        if point["visit_index"] == VISITS[0]
                    )
                ]["valid_start_counter"]
                - 1_200_000
            )
            / 10.0,
            "primary_residual_deg": primary_fit["boundary_residual_deg"],
            "analysis_window_center_separation_us": float(
                np.diff(boundary_times)[0] * 1e6
            ),
            "expected_east_west_phase_change_deg": boundary_east_west_change,
            "expected_east_west_phase_change_reversed_deg": (
                -boundary_east_west_change
            ),
            "bootstrap_median_deg": float(np.median(bootstrap_array)),
            "bootstrap_5_95_deg": np.quantile(bootstrap_array, [0.05, 0.95]).tolist(),
            "bootstrap_rms_deg": float(np.sqrt(np.mean(bootstrap_array**2))),
            "bootstrap_fraction_within_5_deg": float(np.mean(abs(bootstrap_array) < 5.0)),
        },
        "window_sensitivity": window_sensitivity,
        "degree_sensitivity": degree_sensitivity,
        "candidate_center_to_center_phase_change_deg": expected_center_changes,
        "east_west_geometry": {
            "physical_alignment": "horizontal east–west",
            "receiver_order_sign_known": False,
            "center_to_center_phase_change_deg": expected_center_changes[
                east_west_label
            ],
            "center_to_center_phase_change_reversed_deg": -expected_center_changes[
                east_west_label
            ],
        },
        "frozen_estimator_validation": {
            "selection_policy": (
                "all consecutive visit-index pairs among the 47 exact shared "
                "same-track dwells"
            ),
            "estimator_policy": (
                "4096-sample windows, 2048 stride, degree-2 residual-frequency "
                "polynomial fit to both full dwells; frozen after exploratory "
                "selection of visits 766-767"
            ),
            "pair_count": len(validation_pairs),
            "pairs_within_5_deg": int(np.sum(abs(validation_residual) < 5.0)),
            "fraction_within_5_deg": float(np.mean(abs(validation_residual) < 5.0)),
            "median_absolute_residual_deg": float(np.median(abs(validation_residual))),
            "rms_residual_deg": float(np.sqrt(np.mean(validation_residual**2))),
            "seed_only_boundary_resultant": circular_r(
                seed_only_change, np.ones_like(seed_only_change)
            ),
            "modeled_boundary_resultant": validation_r,
            "modeled_boundary_circular_mean_deg": validation_mean_deg,
            "uniform_phase_null": {
                "trials": UNIFORM_NULL_TRIALS,
                "exceedances": validation_null_exceedances,
                "plus_one_tail_probability": validation_null_p,
            },
            "confirmation_excluding_exploratory_766_767": {
                "pair_count": len(confirmation_phase),
                "resultant": confirmation_r,
                "trials": UNIFORM_NULL_TRIALS,
                "exceedances": confirmation_null_exceedances,
                "plus_one_tail_probability": confirmation_null_p,
            },
            "pairs": validation_pairs,
        },
        "plot_data": {
            "time_s": primary_series["time_s"].tolist(),
            "visit_index": primary_series["visit_index"].tolist(),
            "coherence": primary_series["coherence"].tolist(),
            "corrected_phase_deg": np.degrees(primary_fit["corrected_phase_rad"]).tolist(),
            "bootstrap_boundary_residual_deg": bootstrap,
        },
    }
    return result


def plot(result: dict) -> None:
    plot_data = result["plot_data"]
    time_s = np.asarray(plot_data["time_s"])
    phase_rad = np.radians(plot_data["corrected_phase_deg"])
    visits = np.asarray(plot_data["visit_index"])
    boundary = int(np.flatnonzero(visits[1:] != visits[:-1])[0])
    unwrapped = np.unwrap(phase_rad)
    unwrapped -= unwrapped[boundary]
    boundary_time = (time_s[boundary] + time_s[boundary + 1]) / 2
    relative_ms = (time_s - boundary_time) * 1000

    figure, axes = plt.subplots(2, 1, figsize=(12.5, 8.0), sharex=False)
    for visit, color in zip(VISITS, ("tab:blue", "tab:orange"), strict=True):
        keep = visits == visit
        axes[0].plot(
            (time_s[keep] - time_s[0]) * 1000,
            np.degrees(unwrapped[keep]),
            ".-",
            markersize=2,
            linewidth=0.8,
            color=color,
            label=f"visit {visit}",
        )
    axes[0].axvline((boundary_time - time_s[0]) * 1000, color="0.2", linewidth=0.8)
    axes[0].set_xlabel("time from first analysis window (ms)")
    axes[0].set_ylabel("carrier-corrected phase (deg)\n(common arbitrary gauge)")
    axes[0].set_title("Two consecutive dwells on one global device-counter phase axis")
    axes[0].grid(alpha=0.22)
    axes[0].legend(frameon=False)

    zoom = abs(relative_ms) <= 8.0
    axes[1].plot(
        relative_ms[zoom],
        np.degrees(unwrapped[zoom]),
        ".-",
        color="tab:blue",
        markersize=4,
        linewidth=1.2,
    )
    axes[1].axvline(0.0, color="0.2", linewidth=0.8)
    axes[1].set_xlabel("time from dwell boundary (ms)")
    axes[1].set_ylabel("carrier-corrected phase (deg)")
    axes[1].set_title(
        f"Boundary prediction residual = {result['boundary']['primary_residual_deg']:+.2f}° "
        "(boundary excluded from fit)"
    )
    axes[1].grid(alpha=0.22)
    figure.suptitle("Direct-IQ phase bridge: visits 766→767")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "visit-766-767-phase-bridge.png", dpi=180, facecolor="white")
    plt.close(figure)

    figure, axes = plt.subplots(1, 3, figsize=(14.0, 4.7))
    windows = result["window_sensitivity"]
    axes[0].plot(
        [row["window_samples"] for row in windows],
        [row["boundary_residual_deg"] for row in windows],
        "o-",
    )
    axes[0].axhline(0.0, color="0.2", linewidth=0.8)
    axes[0].set_xscale("log", base=2)
    axes[0].set_xlabel("window length (samples)")
    axes[0].set_ylabel("held boundary residual (deg)")
    axes[0].set_title("Window sensitivity")
    axes[0].grid(alpha=0.22)
    degrees = result["degree_sensitivity"]
    axes[1].plot(
        [row["frequency_polynomial_degree"] for row in degrees],
        [row["boundary_residual_deg"] for row in degrees],
        "o-",
    )
    axes[1].axhline(0.0, color="0.2", linewidth=0.8)
    axes[1].set_xlabel("frequency polynomial degree")
    axes[1].set_ylabel("held boundary residual (deg)")
    axes[1].set_title("Carrier-model sensitivity")
    axes[1].grid(alpha=0.22)
    bootstrap = np.asarray(result["plot_data"]["bootstrap_boundary_residual_deg"])
    axes[2].hist(bootstrap, bins=35)
    axes[2].axvline(0.0, color="0.2", linewidth=0.8)
    axes[2].set_xlabel("held boundary residual (deg)")
    axes[2].set_ylabel("random fits")
    axes[2].set_title("2,000 random half-point fits")
    axes[2].grid(alpha=0.22)
    figure.suptitle("Phase-bridge robustness checks")
    figure.tight_layout()
    figure.savefig(REPORT_DIR / "phase-bridge-sensitivity.png", dpi=180, facecolor="white")
    plt.close(figure)

    validation = result["frozen_estimator_validation"]
    pairs = validation["pairs"]
    labels = [f"{row['visits'][0]}→{row['visits'][1]}" for row in pairs]
    residual = np.asarray([row["held_boundary_residual_deg"] for row in pairs])
    expected = np.asarray(
        [row["expected_east_west_boundary_change_deg"] for row in pairs]
    )
    quality = np.asarray(
        [row["minimum_median_direct_coherence"] for row in pairs]
    )
    figure, axes = plt.subplots(2, 1, figsize=(13.5, 8.5), sharex=False)
    colors = plt.get_cmap("viridis")(
        np.clip((quality - quality.min()) / max(np.ptp(quality), 1e-12), 0.0, 1.0)
    )
    axes[0].bar(np.arange(len(pairs)), residual, color=colors)
    axes[0].plot(np.arange(len(pairs)), expected, "k_", markersize=10, label="expected E–W")
    axes[0].axhspan(-5.0, 5.0, color="0.92", zorder=-1, label="±5°")
    axes[0].axhline(0.0, color="0.2", linewidth=0.8)
    axes[0].set_xticks(np.arange(len(pairs)), labels, rotation=35, ha="right")
    axes[0].set_ylabel("held boundary residual (deg)")
    axes[0].set_title(
        "Frozen estimator on every consecutive shared-dwell pair; "
        f"circular R={validation['modeled_boundary_resultant']:.3f}"
    )
    axes[0].legend(frameon=False, ncol=2)
    axes[0].grid(axis="y", alpha=0.22)
    axes[1].scatter(quality, abs(residual), c=colors, s=55)
    for label, x_value, y_value in zip(labels, quality, abs(residual), strict=True):
        axes[1].annotate(label, (x_value, y_value), xytext=(3, 3), textcoords="offset points")
    axes[1].axhline(5.0, color="0.35", linewidth=0.8, linestyle="--")
    axes[1].set_xlabel("minimum median direct coherence across the two dwells")
    axes[1].set_ylabel("absolute held boundary residual (deg)")
    axes[1].set_title("Phase-blind coherence is useful, but not a proven gate")
    axes[1].grid(alpha=0.22)
    figure.suptitle("Adjacent-dwell phase transport: honest cross-pair check")
    figure.tight_layout()
    figure.savefig(
        REPORT_DIR / "all-consecutive-pair-validation.png", dpi=180, facecolor="white"
    )
    plt.close(figure)


def main() -> None:
    result = analyze()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    plot(result)
    print(json.dumps({key: value for key, value in result.items() if key != "plot_data"}, indent=2))


if __name__ == "__main__":
    main()
