"""Postfit GPS diagnostics for blind joint radio/orbit covariance searches."""

import argparse
import csv
import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_joint_marginal import JointMarginal
from dsx01_robust_joint import RobustJoint
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import CENTER
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT
from run_dsx01_robust_empirical import RobustEmpirical

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

matplotlib.use("Agg")
import matplotlib.pyplot as plt

VARIANTS = ("fixed", "radio_noise", "empirical", "robust", "robust_empirical")
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))


class EvaluationAdapter:
    def __init__(self, problem):
        self.problem = problem

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def association_state(self, x):
        state = self.problem.state(x)
        state["marginal_orbit_coefficients"] = {j: [] for j in self.problem.supported}
        return state

    def predicted(self, x):
        return self.problem.conditional_frequency(x)


def problem_for(scan, fit, variant):
    cls = (
        RobustEmpirical
        if variant == "robust_empirical"
        else RobustJoint
        if variant == "robust"
        else JointMarginal
    )
    return cls(
        scan,
        dict(rows=fit["rows"], state=fit["state"]),
        len(fit["state"]["beta"]) == 9,
        variant="empirical" if variant == "robust_empirical" else variant,
        sigma=fit["diagnostics"]["noise_sigma_hz"],
        reference=np.array(fit["diagnostics"]["phase_reference_s"]),
        aliases=fit["aliases"],
    )


def reference_xy():
    return np.array(
        [
            (REFERENCE[1] - CENTER[1]) * 111.32 * np.cos(np.deg2rad(CENTER[0])),
            (REFERENCE[0] - CENTER[0]) * 111,
        ]
    )


def dump_csv(path, rows):
    with path.open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def objective_parts(problem, result):
    """Additive cost accounting, not evidence of which satellite label is true."""
    p = problem
    weight = result.get("noise_precision", np.ones(len(p.slices)))
    counts = np.array([sl.stop - sl.start for sl in p.slices])
    alpha = (4 + counts) / 2
    ratio = alpha / weight / 2
    gamma = (
        np.maximum(0, 2 * alpha * (np.log(ratio) + 1 / ratio - 1))
        if "noise_precision" in result
        else np.zeros(len(counts))
    )
    constants = result["coefficient"][-len(p.slices) :] ** 2
    curve = np.array(
        [
            weight[k] * np.sum((result["conditional_residual_hz"][sl] / p.sigma) ** 2)
            + gamma[k]
            + constants[k]
            + np.sum((np.maximum(0, -result["elevation"][sl]) / 2) ** 2)
            for k, sl in enumerate(p.slices)
        ]
    )
    global_prior = float(np.sum(result["coefficient"][: -len(p.slices)] ** 2))
    return dict(
        curve=curve,
        shared_prior=global_prior,
        logvolume=result["logvolume"],
        total=float(curve.sum() + global_prior + result["logvolume"]),
    )


def plot(rows):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        values = np.array(
            [
                [
                    next(
                        (
                            r["position_error_km"]
                            for r in rows
                            if r["case"] == c
                            and r["variant"] == v
                            and r["arm"] == arm
                            and r["final"]
                        ),
                        np.nan,
                    )
                    for c in CASES
                ]
                for v in VARIANTS
            ]
        )
        im = ax.imshow(values, aspect="auto", vmin=0, vmax=8, cmap="YlOrRd")
        ax.set(
            xticks=range(5),
            xticklabels=[c[-3:] for c in CASES],
            yticks=range(len(VARIANTS)),
            yticklabels=VARIANTS,
            title=arm,
        )
        for (i, j), value in np.ndenumerate(values):
            if np.isfinite(value):
                ax.text(
                    j,
                    i,
                    f"{value:.3f}",
                    ha="center",
                    va="center",
                    color="white" if value > 5 else "black",
                )
    fig.subplots_adjust(left=0.1, right=0.84, wspace=0.4, bottom=0.15)
    fig.colorbar(im, cax=fig.add_axes([0.9, 0.15, 0.015, 0.7]), label="Position error (km)")
    fig.savefig(OUTPUT / "joint_position_errors.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for case in CASES:
        for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
            data = [
                r
                for r in rows
                if r["case"] == case and r["variant"] == "robust" and r["arm"] == arm
            ]
            if data:
                ax.plot(
                    [r["round"] for r in data],
                    [r["position_error_km"] for r in data],
                    "o-",
                    label=case[-3:],
                )
            ax.axhline(1, color="gray", ls=":")
            ax.set(xlabel="Phase linearization round", ylabel="Position error (km)", title=arm)
    axes[-1].legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "robust_rounds.png", dpi=180)
    plt.close(fig)


def run(*, include_rounds=False):
    rows, ablations, drivers, bindings = [], [], {}, {}
    for case in CASES:
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        for variant in VARIANTS:
            path = (
                OUTPUT / "robust_empirical" / case / "empirical/rounds.json"
                if variant == "robust_empirical"
                else OUTPUT / case / variant / "rounds.json"
            )
            if not path.exists():
                continue
            bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            records = json.loads(path.read_text())
            for record in records if include_rounds else records[-1:]:
                iteration, metrics_by_arm = record["iteration"], {}
                fits = record["fits"]
                assert fits["c0"]["rows"] == fits["fitted_c"]["rows"]
                assert fits["c0"]["aliases"] == fits["fitted_c"]["aliases"]
                assert fits["c0"]["starts"] == fits["fitted_c"]["starts"]
                assert (
                    fits["c0"]["diagnostics"]["phase_reference_s"]
                    == fits["fitted_c"]["diagnostics"]["phase_reference_s"]
                )
                for arm, fit in fits.items():
                    p = problem_for(scan, fit, variant)
                    x = np.array(fit["parameters"])
                    z = p.residual(x)
                    replay_error = abs(float(z @ z) - fit["frequency_prior_score"])
                    if replay_error > 1e-5:
                        raise ValueError(
                            f"objective replay differs: {case}/{variant}/{arm}: {replay_error}"
                        )
                    adapter = EvaluationAdapter(p)
                    metrics = nominated_metrics(
                        scan,
                        dict(fit=fit, method="receiver_smooth", arm=arm),
                        problem_factory=lambda *args, adapter=adapter: adapter,
                    )
                    metrics_by_arm[arm] = metrics
                    result = p.calculate(x)
                    at_gps = x.copy()
                    at_gps[:2] = reference_xy()
                    gps_result = p.calculate(at_gps)
                    gps_residual = p.residual(at_gps)
                    parts = objective_parts(p, result)
                    gps_parts = objective_parts(p, gps_result)
                    if abs(parts["total"] - float(z @ z)) > 1e-5:
                        raise ValueError("component decomposition does not match objective")
                    state = p.state(x)
                    exact = paired_phase_frequency(
                        p.sky,
                        p.flat_times,
                        p.flat_labels,
                        state["phases"][p.labels],
                        fit["latitude_deg"],
                        fit["longitude_deg"],
                    )[0]
                    approximation = (
                        result["intercept"]
                        + result["derivative"] * state["phases"][p.labels][p.flat_labels]
                    )
                    linearization_rms = float(
                        np.sqrt(np.mean((p.q * (exact - approximation)) ** 2))
                    )
                    row = dict(
                        case=case,
                        variant=variant,
                        arm=arm,
                        round=iteration,
                        final=iteration == records[-1]["iteration"],
                        position_error_km=distance_km(
                            (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                        ),
                        frequency_score=fit["frequency_prior_score"],
                        gps_frequency_score_same_hyper=float(gps_residual @ gps_residual),
                        quadratic=result["quadratic"],
                        logvolume=result["logvolume"],
                        gamma_cost=result.get("gamma_cost", 0.0),
                        accepted_curved_points=metrics["accepted_nominated_curved_points"],
                        accepted_curves=sum(t["compatible"] for t in metrics["tracks"]),
                        native_rms_hz=metrics["accepted_native_rms_hz"],
                        linearization_rms_hz=linearization_rms,
                        replay_error=replay_error,
                        radio_noise_hz=p.sigma,
                        rx_drift_mean_sigma=fit["diagnostics"]["rx_drift_mean_sigma_hz_s"],
                        rx_smooth_sigma=fit["diagnostics"]["rx_smooth_sigma_hz"],
                        orbital_scale=fit["diagnostics"]["physical_orbit_scale"],
                        weak_noise_precision_curves=int(
                            np.sum(result.get("noise_precision", np.ones(len(p.members))) < 0.2)
                        ),
                    )
                    rows.append(row)
                    per_curve = []
                    for k, (i, sl) in enumerate(zip(p.members, p.slices, strict=True)):
                        t = scan.tracks[i]
                        gps_square = float(
                            np.sum((gps_result["conditional_residual_hz"][sl] / p.sigma) ** 2)
                        )
                        endpoint_square = float(
                            np.sum((result["conditional_residual_hz"][sl] / p.sigma) ** 2)
                        )
                        per_curve.append(
                            dict(
                                component=t["key"],
                                points=sl.stop - sl.start,
                                conditional_white_square_at_gps=gps_square,
                                conditional_white_square_at_endpoint=endpoint_square,
                                difference=gps_square - endpoint_square,
                                objective_at_gps=float(gps_parts["curve"][k]),
                                objective_at_endpoint=float(parts["curve"][k]),
                                objective_difference=float(
                                    gps_parts["curve"][k] - parts["curve"][k]
                                ),
                            )
                        )
                    drivers[f"{case}/{variant}/{iteration}/{arm}"] = dict(
                        tracks=sorted(per_curve, key=lambda r: -r["objective_difference"]),
                        endpoint_shared_prior=parts["shared_prior"],
                        gps_shared_prior=gps_parts["shared_prior"],
                        endpoint_logvolume=parts["logvolume"],
                        gps_logvolume=gps_parts["logvolume"],
                        native_gates=metrics["tracks"],
                        noise_precision=result.get("noise_precision"),
                        note=(
                            "Objective differences include conditional data, curve-constant "
                            "prior, Gamma and visibility terms; shared priors/volume are separate."
                        ),
                    )
                common = {
                    r["component"] for r in metrics_by_arm["c0"]["tracks"] if r["compatible"]
                } & {
                    r["component"] for r in metrics_by_arm["fitted_c"]["tracks"] if r["compatible"]
                }
                item = dict(case=case, variant=variant, round=iteration, common_points=0)
                for arm in ("c0", "fitted_c"):
                    data = [r for r in metrics_by_arm[arm]["tracks"] if r["component"] in common]
                    n = sum(r["points"] for r in data)
                    item["common_points"] = n
                    item["native_rms_" + arm + "_hz"] = float(
                        np.sqrt(sum(r["native_square_hz2"] for r in data) / max(1, n))
                    )
                ablations.append(item)
    write(OUTPUT / "evaluation_summary.json", rows)
    dump_csv(OUTPUT / "evaluation_summary.csv", rows)
    write(OUTPUT / "c_ablation.json", ablations)
    dump_csv(OUTPUT / "c_ablation.csv", ablations)
    write(OUTPUT / "false_basin_drivers.json", drivers)
    write(OUTPUT / "evaluation_bindings.json", bindings)
    plot(rows)
    print(
        json.dumps(
            dict(
                records=len(rows),
                matched_c_pairs=len(ablations),
                max_replay_error=max(r["replay_error"] for r in rows),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-rounds", action="store_true")
    run(include_rounds=parser.parse_args().include_rounds)
