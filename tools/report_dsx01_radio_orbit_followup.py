"""Replay completed blind radio/orbit followups; coordinates enter evaluation only."""

import argparse
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_all_candidate_uncertainty import all_candidate_problem
from dsx01_combined_radio import CombinedRadio
from dsx01_independent_band_drift import IndependentBands
from dsx01_precise_window import PreciseWindow
from dsx01_relinearized_orbits import RelinearizedOrbits
from dsx01_robust_joint import RobustJoint
from dsx01_robust_joint import student_joint_bound as original_bound
from dsx01_window_noise import WindowNoise
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import EvaluationAdapter, dump_csv, reference_xy
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from run_dsx01_clock_transfer import measurement_path

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = ROOT / "reports/2026_10_18_dsx01_radio_orbit_followup"
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
SPECS = {
    "baseline": ("joint_marginal", "robust", RobustJoint, 3),
    "independent_2": ("independent_band_drift", "independent_2", IndependentBands, 3),
    "independent_10": ("independent_band_drift", "independent_10", IndependentBands, 3),
    **{
        key: ("relinearized_orbits", key, RelinearizedOrbits, 4)
        for key in ("fixed_3", "relinearized_3", "fixed_5", "relinearized_5")
    },
    "window_noise": ("window_noise", "window_noise", WindowNoise, 3),
    "window_precise": ("precision_control", "window_precise", PreciseWindow, 3),
    **{
        key: ("combined_radio", key, CombinedRadio, 3)
        for key in ("window_independent_2", "window_independent_10")
    },
    **{
        key: ("all_candidate_uncertainty", key, all_candidate_problem, 3)
        for key in ("all_3", "all_5", "all_3_window")
    },
}


def problem_for(scan, fit, variant):
    _, configuration, cls, _ = SPECS[variant]
    diagnostics = fit["diagnostics"]
    kwargs = dict(
        variant=configuration,
        sigma=diagnostics["noise_sigma_hz"],
        reference=np.array(diagnostics["phase_reference_s"]),
        aliases=fit["aliases"],
    )
    if cls is RelinearizedOrbits:
        kwargs["orbit_reference"] = diagnostics["orbit_reference_standard"]
    if "point_noise_sigma_hz" in diagnostics:
        kwargs["point_noise"] = diagnostics["point_noise_sigma_hz"]
    return cls(
        scan,
        dict(rows=fit["rows"], state=fit["state"]),
        len(fit["state"]["beta"]) == 9,
        **kwargs,
    )


def cost_parts(problem, x):
    p = problem
    result = p.calculate(x)
    sigma = getattr(p, "point_noise", p.sigma)
    weight = result["noise_precision"][p.noise_groups]
    native = result["conditional_residual_hz"]
    coefficient = result["coefficient"]
    constants = len(p.slices)
    parts = dict(
        weighted_data=float(np.sum(weight * (native / sigma) ** 2)),
        shared_prior=float(np.sum(coefficient[:-constants] ** 2)),
        curve_constant_prior=float(np.sum(coefficient[-constants:] ** 2)),
        gamma_cost=result["gamma_cost"],
        nuisance_logvolume=result["logvolume"],
        visibility=float(np.sum((np.maximum(0, -result["elevation"]) / 2) ** 2)),
        # Restore the omitted fixed white-noise volume before comparing models.
        diagonal_noise_logvolume=float(2 * np.log(np.broadcast_to(sigma, native.shape) / 40).sum()),
    )
    parts["normalized_total"] = float(sum(parts.values()))
    return parts


def matched_controls(fits):
    a, b = fits["c0"], fits["fitted_c"]
    for key in ("rows", "aliases", "starts", "grid"):
        if a[key] != b[key]:
            raise ValueError(f"unmatched c arms: {key}")
    for key in ("phase_reference_s", "orbit_reference_standard", "point_noise_sigma_hz"):
        if a["diagnostics"].get(key) != b["diagnostics"].get(key):
            raise ValueError(f"unmatched c arms: {key}")


def figures(rows, details):
    variants = list(dict.fromkeys(r["variant"] for r in rows))
    fig, axes = plt.subplots(1, 2, figsize=(15, max(7, len(variants) * 0.58)))
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        values = np.array(
            [
                [
                    next(
                        r["position_error_km"]
                        for r in rows
                        if r["case"] == c and r["variant"] == v and r["arm"] == arm and r["final"]
                    )
                    for c in CASES
                ]
                for v in variants
            ]
        )
        im = ax.imshow(values, vmin=0, vmax=3, cmap="YlOrRd", aspect="auto")
        ax.set(
            xticks=range(5),
            xticklabels=[c[-3:] for c in CASES],
            yticks=range(len(variants)),
            yticklabels=variants,
            title=arm,
        )
        for (i, j), value in np.ndenumerate(values):
            ax.text(
                j,
                i,
                f"{value:.3f}",
                ha="center",
                va="center",
                color="white" if value > 2 else "black",
            )
    fig.subplots_adjust(left=0.17, right=0.86, wspace=0.6)
    fig.colorbar(im, cax=fig.add_axes([0.91, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "position_errors.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for variant in ("fixed_3", "relinearized_3", "fixed_5", "relinearized_5"):
        final = [r for r in rows if r["variant"] == variant and r["final"] and r["arm"] == "c0"]
        if not final:
            continue
        axes[0].plot(range(5), [r["exact_mean_rms_hz"] for r in final], "o-", label=variant)
        axes[1].plot(range(5), [r["position_error_km"] for r in final], "o-", label=variant)
    for ax in axes:
        ax.set(xticks=range(5), xticklabels=[c[-3:] for c in CASES])
    axes[0].set(ylabel="Conditional tangent vs exact SGP4 RMS (Hz)", yscale="log")
    axes[1].set(ylabel="Independent position error (km)")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / "relinearization_controls.png", dpi=150)
    plt.close(fig)
    info_path = ROOT / "reports/2026_10_18_dsx01_radio_drift_information/information.json"
    info = json.loads(info_path.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for key, label in (
        ("common_RX_mean_Hz_s", "Common RX mean"),
        ("RX2_minus_RX1_mean_Hz_s", "RX2 minus RX1 mean"),
        ("RX1_half_high_minus_low_Hz_s", "RX1 band half-contrast"),
        ("RX2_half_high_minus_low_Hz_s", "RX2 band half-contrast"),
    ):
        axes[0].plot(
            range(5),
            [info[c]["c0"]["target_information"][key]["nominal_sigma"] for c in CASES],
            "o-",
            label=label,
        )
    axes[1].bar(range(5), [info[c]["c0"]["standardized_radio_model_RMS"] for c in CASES])
    axes[1].axhline(1, color="black", linestyle="--")
    for ax in axes:
        ax.set(xticks=range(5), xticklabels=[c[-3:] for c in CASES])
    axes[0].set(ylabel="Nominal model-conditional rate uncertainty (Hz/s)", yscale="log")
    axes[0].legend(fontsize=8)
    axes[1].set(ylabel="Radio-only family polynomial standardized RMS")
    fig.tight_layout()
    fig.savefig(OUTPUT / "radio_drift_information.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, case in zip(axes, ("DSX01-S03", "DSX01-S05"), strict=True):
        selected = [
            v
            for v in ("baseline", "window_noise", "independent_2", "all_3_window")
            if f"{case}/{v}/c0" in details
        ]
        positive, negative = np.zeros(len(selected)), np.zeros(len(selected))
        for key in (
            "weighted_data",
            "shared_prior",
            "curve_constant_prior",
            "gamma_cost",
            "nuisance_logvolume",
        ):
            values = np.array(
                [details[f"{case}/{v}/c0"]["GPS_minus_endpoint_cost"][key] for v in selected]
            )
            base = np.where(values >= 0, positive, negative)
            ax.bar(range(len(selected)), values, bottom=base, label=key)
            positive += np.maximum(0, values)
            negative += np.minimum(0, values)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set(
            xticks=range(len(selected)),
            xticklabels=selected,
            title=case,
            ylabel="Cost at evaluation GPS minus blind endpoint",
        )
        ax.tick_params(axis="x", rotation=25)
    axes[-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUTPUT / "wrong_position_cost_drivers.png", dpi=150)
    plt.close(fig)


def run(variants):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, ablations, details, bindings = [], [], {}, {}
    for case in CASES:
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        for variant in variants:
            root, configuration, _, count = SPECS[variant]
            path = ROOT / f"reports/2026_10_18_dsx01_{root}" / case / configuration / "rounds.json"
            records = json.loads(path.read_text())
            if len(records) != count:
                raise ValueError(f"incomplete run: {path}: {len(records)}/{count}")
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            for record in records:
                fits, pair = record["fits"], {}
                matched_controls(fits)
                for arm, fit in fits.items():
                    p = problem_for(scan, fit, variant)
                    x = np.array(fit["parameters"])
                    z = p.residual(x)
                    replay = abs(float(z @ z) - fit["frequency_prior_score"])
                    if replay > 1e-5:
                        raise ValueError(
                            f"objective replay failed: {case}/{variant}/{arm}: {replay}"
                        )
                    backend_replay = None
                    if variant == "window_precise":
                        result = p.calculate(x)
                        oracle = original_bound(
                            p.values - p.q * result["intercept"],
                            result["features"],
                            p.point_noise,
                            p.noise_groups,
                            iterations=256,
                        )
                        oracle_score = (
                            oracle["residual"] @ oracle["residual"]
                            + p.diagonal_logvolume
                            + np.sum((np.maximum(0, -result["elevation"]) / 2) ** 2)
                        )
                        backend_replay = abs(float(oracle_score) - fit["frequency_prior_score"])
                        if backend_replay > 1e-5:
                            raise ValueError(f"precision backend replay failed: {case}/{arm}")
                    final = record is records[-1]
                    row = dict(
                        case=case,
                        variant=variant,
                        arm=arm,
                        round=record["iteration"],
                        final=final,
                        position_error_km=distance_km(
                            (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                        ),
                        objective_replay_error=replay,
                        independent_backend_replay_error=backend_replay,
                        frequency_prior_score=fit["frequency_prior_score"],
                        original_curved_points=len(p.values),
                        exact_mean_rms_hz=fit["diagnostics"].get("exact_sgp4_mean_rms_hz"),
                        white_gate_points=None,
                        white_gate_curves=None,
                        white_gate_native_rms_hz=None,
                        normalized_total=None,
                    )
                    if final:
                        parts = cost_parts(p, x)
                        truth_parts = cost_parts(p, reference_xy())
                        adapter = EvaluationAdapter(p)
                        metrics = nominated_metrics(
                            scan,
                            dict(fit=fit, method="receiver_smooth", arm=arm),
                            problem_factory=lambda *args, adapter=adapter: adapter,
                        )
                        pair[arm] = metrics
                        row.update(
                            white_gate_points=metrics["accepted_nominated_curved_points"],
                            white_gate_curves=sum(t["compatible"] for t in metrics["tracks"]),
                            white_gate_native_rms_hz=metrics["accepted_native_rms_hz"],
                            normalized_total=parts["normalized_total"],
                        )
                        details[f"{case}/{variant}/{arm}"] = dict(
                            native_gate=metrics,
                            endpoint_cost=parts,
                            evaluation_GPS_cost=truth_parts,
                            GPS_minus_endpoint_cost={k: truth_parts[k] - parts[k] for k in parts},
                            GPS_used_only_here_postfit=True,
                            GPS_cost_uses_same_numerical_phase_and_orbit_reference=True,
                        )
                    rows.append(row)
                if pair:
                    common = set.intersection(
                        *[
                            {t["component"] for t in m["tracks"] if t["compatible"]}
                            for m in pair.values()
                        ]
                    )
                    ablation = dict(case=case, variant=variant)
                    for arm, metrics in pair.items():
                        tracks = [t for t in metrics["tracks"] if t["component"] in common]
                        n = sum(t["points"] for t in tracks)
                        ablation["common_points"] = n
                        ablation[f"native_rms_{arm}_hz"] = float(
                            np.sqrt(sum(t["native_square_hz2"] for t in tracks) / max(1, n))
                        )
                    ablations.append(ablation)
            print(
                json.dumps(dict(case=case, variant=variant, records=len(records) * 2)), flush=True
            )
    write(OUTPUT / "evaluation_summary.json", rows)
    dump_csv(OUTPUT / "evaluation_summary.csv", rows)
    write(OUTPUT / "c_ablation.json", ablations)
    dump_csv(OUTPUT / "c_ablation.csv", ablations)
    write(OUTPUT / "frequency_details.json", details)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    figures(rows, details)
    print(
        json.dumps(
            dict(
                records=len(rows),
                pairs=len(rows) // 2,
                max_replay_error=max(r["objective_replay_error"] for r in rows),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", nargs="+", choices=SPECS, default=list(SPECS))
    run(parser.parse_args().variants)
