"""Replay causal-correlation/forecast fits; evaluate GPS only after fitting."""

import argparse
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_causal_correlation import VARIANTS as CORRELATIONS
from dsx01_causal_correlation import CausalCorrelation
from dsx01_causal_forecast import VARIANTS as FORECASTS
from dsx01_causal_forecast import CausalForecast
from dsx01_joint_exact_mean import exact_conditional_frequency
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import EvaluationAdapter, dump_csv, reference_xy
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from report_dsx01_radio_orbit_followup import matched_controls
from run_dsx01_clock_transfer import measurement_path

OUTPUT = ROOT / "reports/2026_10_18_dsx01_causal_correlation"
CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))
SPECS = {
    **{v: ("causal_correlation", CausalCorrelation) for v in CORRELATIONS},
    **{v: ("causal_forecast", CausalForecast) for v in FORECASTS},
}


def problem_for(scan, fit, variant):
    cls = SPECS[variant][1]
    return cls(
        scan,
        dict(rows=fit["rows"], state=fit["state"]),
        len(fit["state"]["beta"]) == 9,
        variant=variant,
        sigma=fit["diagnostics"]["noise_sigma_hz"],
        reference=np.array(fit["diagnostics"]["phase_reference_s"]),
        aliases=fit["aliases"],
        point_noise=fit["diagnostics"]["point_noise_sigma_hz"],
    )


def parts(p, x):
    r = p.calculate(np.asarray(x))
    z = r["latent_coefficient"]
    stop = len(z) - len(p.members)
    weight = r["noise_precision"][p.noise_groups]
    values = dict(
        weighted_data=float(np.sum(weight * (r["conditional_residual_hz"] / p.point_noise) ** 2)),
        shared_prior=float(z[:stop] @ z[:stop]),
        curve_constant_prior=float(z[stop:] @ z[stop:]),
        noise_gamma=r["noise_gamma_cost"],
        nuisance_logvolume=r["logvolume"],
        diagonal_noise_logvolume=p.diagonal_logvolume,
        visibility=float(np.sum((np.maximum(0, -r["elevation"]) / 2) ** 2)),
    )
    values["relative_total"] = float(sum(values.values()))
    values["full_total"] = values["relative_total"] + r["full_objective_offset"]
    return values


def run(case):
    directory = OUTPUT / "evaluation" / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    rows, details, ablations, bindings = [], {}, [], {}
    for variant, (stem, _) in SPECS.items():
        path = ROOT / f"reports/2026_10_18_dsx01_{stem}" / case / variant / "rounds.json"
        records = json.loads(path.read_text())
        assert len(records) == 3, path
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        old = None
        if variant == "diag_4":
            baseline = (
                ROOT
                / "reports/2026_10_18_dsx01_satellite_prior_controls"
                / case
                / "normal/rounds.json"
            )
            old = json.loads(baseline.read_text())
            bindings[str(baseline.relative_to(ROOT))] = hashlib.sha256(
                baseline.read_bytes()
            ).hexdigest()
        pair = {}
        for record in records:
            fits = record["fits"]
            matched_controls(fits)
            for arm, fit in fits.items():
                p = problem_for(scan, fit, variant)
                x = np.array(fit["parameters"])
                costs = parts(p, x)
                error = abs(costs["relative_total"] - fit["frequency_prior_score"])
                if error > 1e-6:
                    raise ValueError(f"replay failed:{case}/{variant}/{arm}:{error}")
                control_error = None
                if old is not None:
                    previous = old[record["iteration"]]["fits"][arm]
                    control_error = float(np.max(abs(x - np.array(previous["parameters"]))))
                    if (
                        control_error > 1e-8
                        or abs(fit["frequency_prior_score"] - previous["frequency_prior_score"])
                        > 1e-7
                    ):
                        raise ValueError("diagonal4 baseline changed")
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
                    full_score=costs["full_total"],
                    objective_replay_error=error,
                    normal_control_parameter_error=control_error,
                    original_curved_points=len(p.values),
                    white_gate_points=None,
                    white_gate_curves=None,
                    white_gate_rms_hz=None,
                    final_log_precision_change=result["final_log_precision_change"],
                    precision_iterations=result["precision_iterations"],
                    exact_orbit_mean_rms_hz=None,
                    exact_orbit_check_error=None,
                )
                if final:
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
                        white_gate_rms_hz=metrics["accepted_native_rms_hz"],
                    )
                    try:
                        exact, _, _ = exact_conditional_frequency(p, x)
                        tangent, _ = p.conditional_frequency(x)
                        row["exact_orbit_mean_rms_hz"] = float(
                            np.sqrt(np.mean((p.q * (exact - tangent)) ** 2))
                        )
                    except ValueError as exc:
                        row["exact_orbit_check_error"] = str(exc)
                    truth = parts(p, reference_xy())
                    details[f"{variant}/{arm}"] = dict(
                        native_gate=metrics,
                        endpoint_cost=costs,
                        evaluation_GPS_cost=truth,
                        GPS_minus_endpoint_cost={k: truth[k] - costs[k] for k in costs},
                        GPS_only_used_in_postfit_diagnostic=True,
                        forecast_metadata=getattr(p, "forecast_metadata", None),
                        history_selection=getattr(p, "history_selection", None),
                        correlation_metadata=p.correlation_metadata,
                    )
                rows.append(row)
        common = set.intersection(
            *[{t["component"] for t in m["tracks"] if t["compatible"]} for m in pair.values()]
        )
        ablation = dict(case=case, variant=variant)
        for arm, metrics in pair.items():
            selected = [t for t in metrics["tracks"] if t["component"] in common]
            n = sum(t["points"] for t in selected)
            ablation["common_points"] = n
            ablation[f"native_rms_{arm}_hz"] = float(
                np.sqrt(sum(t["native_square_hz2"] for t in selected) / max(1, n))
            )
        ablations.append(ablation)
        print(json.dumps(dict(case=case, variant=variant, records=len(records) * 2)), flush=True)
    for name, value in [
        ("summary", rows),
        ("details", details),
        ("c_ablation", ablations),
        ("bindings", bindings),
    ]:
        write(directory / (name + ".json"), value)
    dump_csv(directory / "summary.csv", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=CASES)
    run(parser.parse_args().case)
