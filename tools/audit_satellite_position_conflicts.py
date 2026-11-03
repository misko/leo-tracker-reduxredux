"""All-point blind-family tangent audit with explicit satellite deletion influences."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from transfer_fixed_satellite_families import ROOT, FixedFamilies

from leo.analysis.research.position_family_influence import tangent_position_step

INPUT = ROOT / "reports/2026_10_17_position_information"
OUTPUT = ROOT / "reports/2026_10_17_family_conflicts_ds22_expansion"


def run():
    output = OUTPUT / "influence"
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for case in ("DSX01-S01", "DS22-001"):
        for fitted_c in (False, True):
            arm = "fitted_c" if fitted_c else "c0"
            original = INPUT / case / f"unmerged_default_{arm}"
            source = (
                ROOT
                / "reports/2026_10_17_fixed_family_transfer/search"
                / case
                / f"unmerged_default_{arm}/fit.json"
            )
            fit = json.loads(source.read_text())["endpoint"]
            study = FixedFamilies(case, fitted_c, False)
            detail = study.evaluate(
                fit["latitude_deg"],
                fit["longitude_deg"],
                np.array(fit["beta"]),
                np.array(fit["phases_s"]),
                details=True,
            )
            residual = np.concatenate([r["residual_hz"] for r in detail["rows"]])
            member_satellite = np.concatenate(
                [np.full(r["points"], r["norad"]) for r in detail["rows"]]
            )
            constants = np.array([c["bias_hz"] for c in detail["components"]])
            nuisance = np.r_[fit["beta"], fit["phases_s"], constants]
            with np.load(original / "jacobians.npz") as arrays:
                a, b, weights, precision = [
                    arrays[k]
                    for k in ("position_hz_per_km", "nuisance", "weights", "prior_precision")
                ]
            full = tangent_position_step(a, b, residual, nuisance, weights, precision)
            rows = []
            for norad in study.norads:
                keep = member_satellite != norad
                deletion = tangent_position_step(
                    a[keep], b[keep], residual[keep], nuisance, weights[keep], precision
                )
                move = deletion["east_north_step_km"] - full["east_north_step_km"]
                rows.append(
                    dict(
                        norad=norad,
                        points=int(np.count_nonzero(~keep)),
                        rms_hz=float(np.sqrt(np.mean(residual[~keep] ** 2))),
                        compatible_points=sum(
                            r["points"]
                            for r in detail["rows"]
                            if r["norad"] == norad and r["compatible"]
                        ),
                        deletion_east_north_delta_km=move,
                        deletion_influence_km=float(np.linalg.norm(move)),
                        local_step_after_deletion_km=deletion["east_north_step_km"],
                    )
                )
            rows.sort(key=lambda r: r["deletion_influence_km"], reverse=True)
            folder = output / case / arm
            folder.mkdir(parents=True)
            write(folder / "full_tangent.json", full)
            write(folder / "satellite_influences.json", rows)
            write(
                folder / "protocol.json",
                dict(
                    source_input=str(original.relative_to(ROOT)),
                    source_fit=str(source.relative_to(ROOT)),
                    observation_ids=study.observation_ids,
                    satellite_labels=member_satellite,
                    no_geographic_reference_used=True,
                    no_identity_truth_available=True,
                    deletion_is_an_influence_diagnostic_not_holdout_or_final_estimator=True,
                    full_fit_retains_all_points=True,
                    no_linear_calibration=True,
                    no_bounds_volume_derivatives_or_nonlinear_refit_in_tangent=True,
                ),
            )
            summary = dict(
                case=case,
                arm=arm,
                full_tangent_step_km=full["east_north_step_km"],
                most_influential=rows[:5],
                satellites=len(rows),
            )
            summaries.append(summary)
            print(json.dumps(summary, default=lambda v: v.tolist()), flush=True)
    write(output / "summary.json", summaries)


if __name__ == "__main__":
    run()
