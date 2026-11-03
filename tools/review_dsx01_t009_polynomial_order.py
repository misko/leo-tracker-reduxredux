"""Repair S01 T009's isolated endpoint before a matched candidate-phase audit."""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from localize_merged_track_catalogue import raw_curvature

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.robust_polynomial_order import polynomial_orders

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"
NOISE = 150.0
CLUTTER_PROBABILITY = 0.02


def piece_prediction(fit, times):
    return np.polynomial.polynomial.polyval(
        (np.asarray(times) - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
    )


def scalar_diagnostics(track, frequency, beta, bias, alias):
    g = matching.group(track)
    hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
    if len(beta) == 9:
        hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
    prediction = track["rf_hz"] / 11.5e9 * frequency + hardware + bias - alias * matching.PERIOD
    residual = track["values"] - prediction
    return dict(
        time_s=track["times"],
        prediction_hz=prediction,
        residual_hz=residual,
        noise=matching.noise_screen(residual, track["times"]),
    )


def candidate_audit(original, repaired, sky, studies, output):
    # Every candidate sees the same 49 bounded absolute phase vectors and the
    # two frozen phase vectors in both c arms. Known supported phases are frozen.
    phase_vectors = [fraction * sky["phase_bound_s"] for fraction in np.linspace(-1, 1, 49)]
    phase_vectors += [np.asarray(studies[arm]["fit"]["phases_s"]) for arm in ("c0", "fitted_c")]
    times = original["times"]
    models = [original, repaired]
    sigma = sky["phase_sigma_s"]
    n_candidates = len(sky["norad"])
    # Explicit cost for the retained but unassociated original point. This is
    # a contrast score with a fixed clutter density, not a probability of ID.
    normal_zero = np.log1p(-CLUTTER_PROBABILITY) - np.log(NOISE * np.sqrt(2 * np.pi))
    background = np.log(CLUTTER_PROBABILITY) - np.log(matching.PERIOD)
    clutter_cost = 2 * (np.logaddexp(normal_zero, background) - background)
    results = {arm: [dict(), dict()] for arm in studies}
    for grid_index, phase in enumerate(phase_vectors):
        geometry = prepare_phase_geometry(sky, times, phase)
        frequency, elevation, derivative = phase_linear_frequency(
            geometry,
            studies["fitted_c"]["fit"]["latitude_deg"],
            studies["fitted_c"]["fit"]["longitude_deg"],
        )
        stats = matching.statistics(
            [(t["key"], [t]) for t in models],
            dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
            {str(original["channel"]): 0.0},
        )
        for arm, study in studies.items():
            fit = study["fit"]
            beta = np.asarray(fit["beta"])
            supported_ids = {
                r["candidate_norad"]
                for r in study["association"]["rows"]
                if r["compatible"] and r["active_curvature"]
            }
            allowed = ~np.isin(sky["norad"], list(supported_ids))
            allowed |= np.abs(phase - np.asarray(fit["phases_s"])) <= 1e-8
            terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)
            for fi, track in enumerate(models):
                n = len(track["times"])
                ix = np.searchsorted(times, track["times"])
                q, g = track["rf_hz"] / 11.5e9, matching.group(track)
                h = q * derivative[:, ix]
                information = np.maximum(
                    0, np.sum(h * h, axis=1) - h.sum(axis=1) ** 2 / (n + NOISE**2 / 1000**2)
                )
                cost = n * terms.score[fi] / NOISE**2 + (phase / sigma) ** 2
                cost += np.log1p(information * sigma**2 / NOISE**2)
                cost += (len(original["times"]) - n) * clutter_cost
                if fi:
                    cost += np.log(len(original["times"]))  # charge the proposed partition
                hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
                if len(beta) == 9:
                    hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                residual = track["values"][None, :] - hardware[None, :] - q * frequency[:, ix]
                residual += terms.aliases[fi, :, None] * matching.PERIOD
                residual -= terms.bias_hz[fi, :, None]
                noise = batch_noise_screen(residual, track["times"])
                passed = allowed & stats["component_visible"][fi]
                passed &= (terms.residual_mse[fi] <= 450**2) & (np.abs(terms.bias_hz[fi]) <= 3000)
                passed &= noise["noise_screen_pass"]
                # Record each candidate's best feasible phase, plus its overall
                # best phase for explaining failures; never select then reject.
                for j in range(n_candidates):
                    state = results[arm][fi].setdefault(int(sky["norad"][j]), {})
                    record = dict(
                        norad=int(sky["norad"][j]),
                        phase_s=float(phase[j]),
                        cost=float(cost[j]),
                        rms_hz=float(np.sqrt(terms.residual_mse[fi, j])),
                        bias_hz=float(terms.bias_hz[fi, j]),
                        native_alias=int(terms.aliases[fi, j]),
                        passing=bool(passed[j]),
                        phase_change_allowed=bool(allowed[j]),
                        grid_index=grid_index,
                    )
                    if "best_any" not in state or cost[j] < state["best_any"]["cost"]:
                        state["best_any"] = record
                    if passed[j] and (
                        "best_passing" not in state or cost[j] < state["best_passing"]["cost"]
                    ):
                        state["best_passing"] = record
        del geometry
    summaries = []
    for arm, models_result in results.items():
        for fi, table in enumerate(models_result):
            feasible = sorted(
                [r["best_passing"] for r in table.values() if "best_passing" in r],
                key=lambda r: r["cost"],
            )
            best_any = sorted([r["best_any"] for r in table.values()], key=lambda r: r["cost"])
            name = "original_27" if fi == 0 else "robust_core_26_plus_one_clutter"
            write(
                output / f"{arm}_{name}_candidates.json",
                dict(candidates=table, passing=feasible, top_scored=best_any[:5]),
            )
            summary = dict(
                arm=arm,
                model=name,
                original_points=len(original["times"]),
                curve_points=len(models[fi]["times"]),
                explicitly_unassociated_points=len(original["times"]) - len(models[fi]["times"]),
                candidate_count=n_candidates,
                phase_vectors=len(phase_vectors),
                passing_candidates=feasible,
                top_scored=best_any[:3],
                measured_curvature=raw_curvature(models[fi]),
            )
            summaries.append(summary)
            if feasible:
                best = feasible[0]
                j = int(np.flatnonzero(sky["norad"] == best["norad"])[0])
                sub = dict(
                    time_s=sky["time_s"],
                    position_km=sky["position_km"][[j]],
                    velocity_km_s=sky["velocity_km_s"][[j]],
                )
                geom = prepare_phase_geometry(sub, models[fi]["times"], best["phase_s"])
                f, _, _ = phase_linear_frequency(
                    geom, studies[arm]["fit"]["latitude_deg"], studies[arm]["fit"]["longitude_deg"]
                )
                detailed = scalar_diagnostics(
                    models[fi],
                    f[0],
                    np.asarray(studies[arm]["fit"]["beta"]),
                    best["bias_hz"],
                    best["native_alias"],
                )
                detailed.update(best)
                write(output / f"{arm}_{name}_best_residuals.json", detailed)
    write(output / "satellite_summary.json", summaries)
    return summaries


def run():
    output = DEEP / "t009_robust_order"
    output.mkdir(exist_ok=False)
    path = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01/tracks.json"
    original = next(t for t in load_tracks(path.parent) if t["key"] == "S01-RX1-CH1-T009")
    fits = polynomial_orders(original["times"], original["values"])
    best = fits[0]
    mask = best["inlier_mask"]
    if np.count_nonzero(mask) != 26 or mask[-1]:
        raise ValueError("observed T009 partition differs from the investigated endpoint case")
    repaired = dict(
        original,
        key=original["key"] + ":robust_core",
        times=original["times"][mask],
        values=original["values"][mask],
        observation_ids=[oid for i, oid in enumerate(original["observation_ids"]) if mask[i]],
    )
    unassociated = [
        dict(
            observation_id=oid,
            time_s=float(original["times"][i]),
            cfo_hz=float(original["values"][i]),
            original_index=int(original["indices"][i]),
            residual_to_core_hz=float(best["residual_hz"][i]),
        )
        for i, oid in enumerate(original["observation_ids"])
        if not mask[i]
    ]
    owned = repaired["observation_ids"] + [r["observation_id"] for r in unassociated]
    assert sorted(owned) == sorted(original["observation_ids"]) and len(set(owned)) == len(owned)
    write(output / "robust_orders.json", fits)
    write(
        output / "proposed_partition.json",
        dict(
            original_component=original["key"],
            original_points=27,
            selected_degree=best["degree"],
            core=dict(
                times=repaired["times"],
                values=repaired["values"],
                observation_ids=repaired["observation_ids"],
            ),
            explicitly_unassociated=unassociated,
            no_points_dropped=True,
            original_catalogue_unchanged=True,
        ),
    )
    ordinary = []
    x = (original["times"] - best["reference_time_s"]) / best["time_scale_s"]
    for degree in range(1, 5):
        design = np.polynomial.polynomial.polyvander(x, degree)
        coefficient = np.linalg.lstsq(design, original["values"], rcond=None)[0]
        residual = original["values"] - design @ coefficient
        q, _ = np.linalg.qr(design)
        leverage = np.sum(q * q, axis=1)
        ordinary.append(
            dict(
                degree=degree,
                rms_hz=float(np.sqrt(np.mean(residual**2))),
                last_residual_hz=float(residual[-1]),
                last_leverage=float(leverage[-1]),
                last_leave_one_out_residual_hz=float(residual[-1] / (1 - leverage[-1])),
                coefficients_hz=coefficient,
                prediction_hz=design @ coefficient,
            )
        )
    write(output / "ordinary_orders.json", ordinary)
    sensitivity = []
    for noise in (100.0, 150.0, 200.0):
        for probability in (0.005, 0.02, 0.05):
            fit = polynomial_orders(
                original["times"],
                original["values"],
                noise_hz=noise,
                clutter_probability=probability,
            )[0]
            sensitivity.append(
                dict(
                    noise_hz=noise,
                    clutter_probability=probability,
                    degree=fit["degree"],
                    curve_points=int(sum(fit["inlier_mask"])),
                    inlier_rms_hz=fit["inlier_rms_hz"],
                    endpoint_assigned=bool(fit["inlier_mask"][-1]),
                )
            )
    write(output / "sensitivity.json", sensitivity)
    dense = np.linspace(original["times"][0], original["times"][-1], 500)
    measured = dense <= repaired["times"][-1]
    fig, axes = plt.subplots(
        2, 1, figsize=(11, 7), constrained_layout=True, gridspec_kw=dict(height_ratios=[2, 1])
    )
    axes[0].scatter(
        repaired["times"],
        repaired["values"] / 1000,
        color="#222222",
        s=26,
        label="26 curve points",
        zorder=4,
    )
    axes[0].scatter(
        original["times"][~mask],
        original["values"][~mask] / 1000,
        marker="x",
        s=90,
        linewidths=2,
        color="#c13b32",
        label="Unassociated endpoint",
        zorder=5,
    )
    axes[0].plot(
        dense,
        np.polynomial.polynomial.polyval(
            (dense - best["reference_time_s"]) / best["time_scale_s"],
            ordinary[-1]["coefficients_hz"],
        )
        / 1000,
        color="#888888",
        linestyle="--",
        label="Original all-point quartic",
    )
    axes[0].plot(
        dense[measured],
        piece_prediction(best, dense[measured]) / 1000,
        color="#237cad",
        label=f"Robust degree {best['degree']} · 26-point support",
    )
    axes[0].plot(
        dense[~measured],
        piece_prediction(best, dense[~measured]) / 1000,
        color="#237cad",
        linestyle=":",
        label="Extrapolation across unobserved gap",
    )
    axes[0].axvspan(repaired["times"][-1], original["times"][-1], alpha=0.15, color="#888888")
    axes[0].annotate(
        f"{best['residual_hz'][-1] / 1000:+.2f} kHz from quadratic",
        (original["times"][-1], original["values"][-1] / 1000),
        xytext=(-170, 35),
        textcoords="offset points",
        color="#c13b32",
        arrowprops=dict(arrowstyle="->", color="#c13b32"),
    )
    axes[0].set(
        title="S01 · RX1/CH1/T009 · endpoint no longer drives polynomial order",
        ylabel="Unwrapped GLRT CFO (kHz)",
    )
    axes[0].legend(fontsize=8)
    axes[1].scatter(
        repaired["times"],
        best["residual_hz"][mask],
        color="#237cad",
        s=24,
        label=f"Quadratic core · RMS {best['inlier_rms_hz']:.1f} Hz",
    )
    axes[1].scatter(
        repaired["times"],
        (original["values"] - ordinary[-1]["prediction_hz"])[mask],
        color="#888888",
        marker="x",
        label="Original quartic residual on same 26 points",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(
        xlabel="Seconds from scan start",
        ylabel="Core residual (Hz)",
        title="Endpoint remains visible above; it is not part of this residual panel",
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.savefig(output / "polynomial_comparison.png", dpi=150)
    plt.close(fig)
    sky_path = DEEP / "frozen_inputs/DSX01-S01/bank.npz"
    sky = dict(np.load(sky_path))
    studies = {
        arm: json.loads((DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json").read_text())[0]
        for arm in ("c0", "fitted_c")
    }
    summaries = candidate_audit(original, repaired, sky, studies, output)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            robust_component_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/robust_polynomial_order.py").read_bytes()
            ).hexdigest(),
            original_tracks_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            bank_sha256=hashlib.sha256(sky_path.read_bytes()).hexdigest(),
            default_noise_hz=NOISE,
            clutter_probability=CLUTTER_PROBABILITY,
            clutter_width_hz=matching.PERIOD,
            degree_penalty="(degree+1)*log(all_original_points)",
            all_points_scored=True,
            data_only_partition=True,
            original_alias_branches_preserved=True,
            no_random_or_time_holdout_for_final_fit=True,
            leave_one_out_only_initializes_em_and_measures_influence=True,
            one_unassociated_point_retained=True,
            no_hardware_refit=True,
            new_phase_calibration_only_from_measured_curved_core=raw_curvature(repaired),
            already_supported_satellite_phases_frozen=True,
            position_fixed_to_supplied_evaluation_site=True,
            original_catalogue_and_association_unchanged=True,
            c0_and_fitted_c_matched_partition_points_candidates_priors_phase_grid_and_budget=True,
        ),
    )
    print(
        json.dumps(
            dict(
                degree=best["degree"],
                core_points=int(sum(mask)),
                inlier_rms_hz=best["inlier_rms_hz"],
                endpoint_residual_hz=best["residual_hz"][-1],
                satellite=summaries,
            ),
            default=lambda v: v.tolist(),
        ),
        flush=True,
    )


if __name__ == "__main__":
    run()
