"""Replay frame-linked fits and gate their actual conditional residuals."""

import argparse
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_frame_joint import VARIANTS, FrameJoint
from dsx01_joint_exact_mean import exact_conditional_frequency
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_remeasured_position import apply_measurements
from report_dsx01_joint_marginal import EvaluationAdapter, dump_csv, reference_xy
from report_dsx01_model_iterations import REFERENCE, nominated_metrics
from report_dsx01_radio_orbit_followup import matched_controls
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_frame_joint import OUTPUT

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

CASES = tuple(f"DSX01-S0{k}" for k in range(1, 6))


def conditional_gate(residual, times):
    r = np.asarray(residual, float)
    screen = batch_noise_screen(r[None, :], times)
    return dict(
        compatible=bool(screen["noise_screen_pass"][0] and np.sqrt(np.mean(r * r)) <= 450),
        rms_hz=float(np.sqrt(np.mean(r * r))),
        mean_hz=float(np.mean(r)),
        diagnostics={key: value[0] for key, value in screen.items()},
    )


def problem_for(scan, fit, variant):
    return FrameJoint(
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
    result = p.calculate(np.asarray(x))
    z = result["latent_coefficient"]
    stop = len(z) - len(p.members)
    weight = result["noise_precision"][p.noise_groups]
    values = dict(
        weighted_data=float(
            np.sum(weight * (result["conditional_residual_hz"] / p.point_noise) ** 2)
        ),
        shared_prior=float(z[:stop] @ z[:stop]),
        curve_constant_prior=float(z[stop:] @ z[stop:]),
        noise_gamma=result["noise_gamma_cost"],
        nuisance_logvolume=result["logvolume"],
        diagonal_noise_logvolume=p.diagonal_logvolume,
        visibility=float(np.sum((np.maximum(0, -result["elevation"]) / 2) ** 2)),
    )
    values["relative_total"] = float(sum(values.values()))
    values["full_total"] = values["relative_total"] + result["full_objective_offset"]
    return values


def actual_metrics(p, fit, arm, x):
    adapter = EvaluationAdapter(p)
    original = nominated_metrics(
        p.scan,
        dict(fit=fit, method="receiver_smooth", arm=arm),
        problem_factory=lambda *args: adapter,
    )
    result = p.calculate(x)
    rows = []
    for row, i, sl in zip(original["tracks"], p.members, p.slices, strict=True):
        gate = conditional_gate(result["conditional_residual_hz"][sl], p.scan.tracks[i]["times"])
        rows.append(
            dict(
                row,
                original_profile_compatible=row["compatible"],
                profile_native_square_hz2=row["native_square_hz2"],
                native_square_hz2=float(np.sum(result["conditional_residual_hz"][sl] ** 2)),
                native_rms_hz=gate["rms_hz"],
                conditional_residual_gate=gate,
                compatible=row["compatible"] and gate["compatible"] and row["aliases_changed"] == 0,
            )
        )
    while True:
        owners = {}
        for row, i in zip(rows, p.members, strict=True):
            if row["compatible"]:
                t = p.scan.tracks[i]
                owners.setdefault(row["candidate_index"], set()).add((t["receiver"], t["channel"]))
        changed = False
        for row in rows:
            if (
                row["compatible"]
                and row["candidate_index"] in p.supported
                and len(owners.get(row["candidate_index"], set())) < 2
            ):
                row["compatible"] = False
                changed = True
        if not changed:
            break
    n = sum(row["points"] for row in rows if row["compatible"])
    return dict(
        original_profile_metrics=original,
        tracks=rows,
        accepted_points=n,
        accepted_tracks=sum(row["compatible"] for row in rows),
        accepted_native_rms_hz=float(
            np.sqrt(sum(row["native_square_hz2"] for row in rows if row["compatible"]) / max(1, n))
        ),
    )


def run(case):
    directory = OUTPUT / "evaluation" / case
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    rows, details, ablations, bindings = [], {}, [], {}
    control = (
        ROOT / "reports/2026_10_18_dsx01_satellite_prior_controls" / case / "normal/rounds.json"
    )
    normal = json.loads(control.read_text())
    bindings[str(control.relative_to(ROOT))] = hashlib.sha256(control.read_bytes()).hexdigest()
    for variant in VARIANTS:
        path = OUTPUT / case / variant / "rounds.json"
        records = json.loads(path.read_text())
        if len(records) != 3:
            raise ValueError(f"incomplete:{path}")
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        pair = {}
        for record in records:
            fits = record["fits"]
            matched_controls(fits)
            if (
                fits["c0"]["diagnostics"]["fragment_noise_groups"]
                != fits["fitted_c"]["diagnostics"]["fragment_noise_groups"]
            ):
                raise ValueError("noise groups differ within c pair")
            for arm, fit in fits.items():
                p = problem_for(scan, fit, variant)
                x = np.asarray(fit["parameters"])
                cost = parts(p, x)
                error = abs(cost["relative_total"] - fit["frequency_prior_score"])
                if error > 1e-6:
                    raise ValueError(f"score replay failed:{variant}:{error}")
                control_error = None
                if variant == "independent":
                    previous = normal[record["iteration"]]["fits"][arm]
                    control_error = float(np.max(abs(x - np.asarray(previous["parameters"]))))
                    if control_error > 1e-8:
                        raise ValueError("independent control differs")
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
                    full_score=cost["full_total"],
                    objective_replay_error=error,
                    normal_control_parameter_error=control_error,
                    original_curved_points=len(p.values),
                    original_profile_accepted_points=None,
                    actual_accepted_points=None,
                    actual_accepted_tracks=None,
                    actual_accepted_rms_hz=None,
                    conditional_rejections_of_original_accepted=None,
                    precision_iterations=result["precision_iterations"],
                    final_log_precision_change=result["final_log_precision_change"],
                    exact_orbit_mean_rms_hz=None,
                    exact_orbit_check_error=None,
                )
                if final:
                    metrics = actual_metrics(p, fit, arm, x)
                    pair[arm] = metrics
                    row.update(
                        original_profile_accepted_points=metrics["original_profile_metrics"][
                            "accepted_nominated_curved_points"
                        ],
                        actual_accepted_points=metrics["accepted_points"],
                        actual_accepted_tracks=metrics["accepted_tracks"],
                        actual_accepted_rms_hz=metrics["accepted_native_rms_hz"],
                        conditional_rejections_of_original_accepted=sum(
                            t["points"]
                            for t in metrics["tracks"]
                            if t["original_profile_compatible"] and not t["compatible"]
                        ),
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
                        metrics=metrics,
                        endpoint_cost=cost,
                        evaluation_GPS_cost=truth,
                        GPS_minus_endpoint_cost={k: truth[k] - cost[k] for k in cost},
                        linked_groups=fit["diagnostics"]["linked_curved_groups"],
                        frame_link_metadata=fit["diagnostics"]["frame_link_metadata"],
                        GPS_only_for_postfit_diagnostic=True,
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
        print(json.dumps(dict(case=case, variant=variant, replayed=6)), flush=True)
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
