"""Replay one scan of satellite-prior, reliability and prior-strength controls."""

import argparse
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_joint_exact_mean import exact_conditional_frequency
from dsx01_joint_rf_time import VARIANTS as RF_TIME
from dsx01_joint_rf_time import JointRFTime
from dsx01_native_drift import VARIANTS as NATIVE
from dsx01_native_drift import NativeDrift, NativeDriftEvaluation
from dsx01_prior_scale_controls import VARIANTS as SCALES
from dsx01_prior_scale_controls import PriorScaleControls
from dsx01_quality_rate_controls import VARIANTS as QUALITY
from dsx01_quality_rate_controls import QualityRateControls
from dsx01_satellite_prior_controls import VARIANTS as PRIORS
from dsx01_satellite_prior_controls import SatellitePriorControls
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import EvaluationAdapter, dump_csv, reference_xy
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from report_dsx01_radio_orbit_followup import matched_controls
from run_dsx01_clock_transfer import measurement_path

OUTPUT = ROOT / "reports/2026_10_18_dsx01_prior_bias_iterations"
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
SPECS = {
    **{v: ("satellite_prior_controls", SatellitePriorControls) for v in PRIORS},
    **{v: ("quality_rate_controls", QualityRateControls) for v in QUALITY},
    **{v: ("prior_scale_controls", PriorScaleControls) for v in SCALES},
    **{v: ("native_drift", NativeDrift) for v in NATIVE},
    **{v: ("joint_rf_time", JointRFTime) for v in RF_TIME},
}


def problem_for(scan, fit, variant):
    _, cls = SPECS[variant]
    seed_state = dict(fit["state"])
    if cls is NativeDrift:
        # The legacy alias constructor expects its original RX basis width.
        # The joint model ignores those warm radio values and reconstructs all
        # nuisance means from data; explicit saved aliases and phase reference
        # below are retained. Never rewrite persisted native coordinates.
        seed_state["smooth"] = np.zeros((2, scan.rx_basis[0].shape[1]))
    return cls(
        scan,
        dict(rows=fit["rows"], state=seed_state),
        len(fit["state"]["beta"]) == 9,
        variant=variant,
        sigma=fit["diagnostics"]["noise_sigma_hz"],
        reference=np.array(fit["diagnostics"]["phase_reference_s"]),
        point_noise=fit["diagnostics"]["point_noise_sigma_hz"],
        aliases=fit["aliases"],
    )


def parts(problem, x):
    p = problem
    result = p.calculate(x)
    coefficient, precision = result["coefficient"], result["coefficient_prior_precision"]
    power = getattr(p, "point_power", np.ones(len(p.values)))
    weight = power * result["noise_precision"][p.noise_groups]
    stop = len(coefficient) - len(p.members)
    values = dict(
        weighted_data=float(
            np.sum(weight * (result["conditional_residual_hz"] / p.point_noise) ** 2)
        ),
        shared_prior=float(np.sum(precision[:stop] * coefficient[:stop] ** 2)),
        curve_constant_prior=float(np.sum(precision[stop:] * coefficient[stop:] ** 2)),
        noise_gamma=result["noise_gamma_cost"],
        prior_gamma=result["prior_gamma_cost"],
        nuisance_logvolume=result["logvolume"],
        diagonal_noise_logvolume=p.diagonal_logvolume,
        visibility=float(np.sum((np.maximum(0, -result["elevation"]) / 2) ** 2)),
    )
    values["relative_total"] = float(sum(values.values()))
    values["full_total"] = values["relative_total"] + result["full_objective_offset"]
    return values


def conditional_covariance(features, sigma, weight, prior_precision):
    u = np.asarray(features) / np.asarray(sigma)[:, None] * np.sqrt(weight)[:, None]
    root = np.linalg.cholesky(np.diag(prior_precision) + u.T @ u)
    inverse_root = np.linalg.solve(root, np.eye(root.shape[0]))
    return inverse_root.T @ inverse_root


def run(case):
    directory = OUTPUT / "evaluation" / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    rows, details, ablations, bindings = [], {}, [], {}
    for variant, (stem, _) in SPECS.items():
        path = ROOT / f"reports/2026_10_18_dsx01_{stem}" / case / variant / "rounds.json"
        records = json.loads(path.read_text())
        if len(records) != 3:
            raise ValueError(f"incomplete run: {path}: {len(records)}/3")
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        legacy = None
        if variant == "normal":
            control = (
                ROOT
                / "reports/2026_10_18_dsx01_precision_control"
                / case
                / "window_precise/rounds.json"
            )
            legacy = json.loads(control.read_text())
            bindings[str(control.relative_to(ROOT))] = hashlib.sha256(
                control.read_bytes()
            ).hexdigest()
        for record in records:
            fits, pair = record["fits"], {}
            matched_controls(fits)
            if fits["c0"]["diagnostics"].get("likelihood_power_by_fragment") != fits["fitted_c"][
                "diagnostics"
            ].get("likelihood_power_by_fragment"):
                raise ValueError("c arms have different calibration powers")
            for arm, fit in fits.items():
                control_error = None
                if legacy is not None:
                    previous = legacy[record["iteration"]]["fits"][arm]
                    control_error = float(
                        np.max(abs(np.array(fit["parameters"]) - np.array(previous["parameters"])))
                    )
                    if (
                        control_error > 1e-8
                        or abs(fit["frequency_prior_score"] - previous["frequency_prior_score"])
                        > 1e-7
                    ):
                        raise ValueError(f"Gaussian control failed to reproduce: {case}/{arm}")
                p = problem_for(scan, fit, variant)
                x = np.array(fit["parameters"])
                score_parts = parts(p, x)
                error = abs(score_parts["relative_total"] - fit["frequency_prior_score"])
                if error > 1e-5:
                    raise ValueError(f"replay failed: {case}/{variant}/{arm}: {error}")
                final = record is records[-1]
                result = p.calculate(x)
                row = dict(
                    case=case,
                    variant=variant,
                    arm=arm,
                    round=record["iteration"],
                    final=final,
                    position_error_km=distance_km(
                        (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                    ),
                    frequency_prior_score=fit["frequency_prior_score"],
                    full_score=score_parts["full_total"],
                    objective_replay_error=error,
                    normal_control_parameter_error=control_error,
                    original_curved_points=len(p.values),
                    effective_observations=result["effective_observations"],
                    generalized_score=bool(np.any(getattr(p, "power", np.ones(len(p.slices))) < 1)),
                    precision_iterations=result["precision_iterations"],
                    final_log_precision_change=result["final_log_precision_change"],
                    white_gate_points=None,
                    white_gate_curves=None,
                    white_gate_rms_hz=None,
                    exact_orbit_mean_rms_hz=None,
                    exact_orbit_check_error=None,
                )
                if final:
                    truth_parts = parts(p, reference_xy())
                    adapter = (
                        NativeDriftEvaluation(p)
                        if isinstance(p, NativeDrift)
                        else EvaluationAdapter(p)
                    )
                    metrics = nominated_metrics(
                        scan,
                        dict(fit=fit, method="receiver_smooth", arm=arm),
                        problem_factory=lambda *args, adapter=adapter: adapter,
                    )
                    pair[arm] = metrics
                    row.update(
                        white_gate_points=metrics["accepted_nominated_curved_points"],
                        white_gate_curves=sum(t["compatible"] for t in metrics["tracks"]),
                        white_gate_rms_hz=metrics["accepted_native_rms_hz"],
                    )
                    try:
                        exact, _, _ = exact_conditional_frequency(p, x)
                        tangent, _ = p.conditional_frequency(x)
                        clock = getattr(p, "clock", np.empty((len(p.values), 0)))
                        begin = result["features"].shape[1] - len(p.members) - clock.shape[1]
                        extra = clock @ result["coefficient"][begin : begin + clock.shape[1]]
                        row["exact_orbit_mean_rms_hz"] = float(
                            np.sqrt(np.mean((p.q * (exact - tangent) + extra) ** 2))
                        )
                    except ValueError as exc:
                        row["exact_orbit_check_error"] = str(exc)
                    details[f"{variant}/{arm}"] = dict(
                        native_gate=metrics,
                        endpoint_cost=score_parts,
                        evaluation_GPS_cost=truth_parts,
                        GPS_minus_endpoint_cost={
                            k: truth_parts[k] - score_parts[k] for k in score_parts
                        },
                        GPS_only_for_postfit_diagnostic=True,
                        prior_group_precision=result["prior_group_precision"],
                        state_additions={
                            k: v
                            for k, v in fit["state"].items()
                            if k.startswith(("satellite_", "receiver_"))
                        },
                    )
                    if isinstance(p, JointRFTime):
                        covariance = conditional_covariance(
                            result["features"],
                            p.point_noise,
                            p.point_power * result["noise_precision"][p.noise_groups],
                            result["coefficient_prior_precision"],
                        )
                        begin = len(result["coefficient"]) - len(p.members) - 2
                        details[f"{variant}/{arm}"]["receiver_RF_rate_conditional_sigma"] = (
                            np.sqrt(np.diag(covariance)[begin : begin + 2]) * p.rf_time_sigma
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
        print(json.dumps(dict(case=case, variant=variant, replayed=len(records) * 2)), flush=True)
    for name, value in [
        ("summary", rows),
        ("details", details),
        ("c_ablation", ablations),
        ("bindings", bindings),
    ]:
        write(directory / (name + ".json"), value)
    dump_csv(directory / "summary.csv", rows)
    print(
        json.dumps(
            dict(
                case=case,
                records=len(rows),
                maximum_replay_error=max(r["objective_replay_error"] for r in rows),
            )
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    run(parser.parse_args().case)
