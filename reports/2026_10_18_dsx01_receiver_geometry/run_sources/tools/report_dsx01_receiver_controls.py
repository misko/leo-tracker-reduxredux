"""Postfit-only frequency/position evaluation of the combined S01 controls."""

import csv
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_family_consensus import ConsensusFamilies
from prototype_dsx01_mean_motion import MotionFamilies, reference_motion_basis
from prototype_dsx01_receiver_geometry import OUTPUT, geometry_problem
from prototype_dsx01_receiver_phase import phase_problem
from prototype_s01_receiver_drift import ReceiverDriftProblem
from report_dsx01_model_iterations import REFERENCE, nominated_metrics


def inputs():
    base = ROOT / "reports"
    p = base / "2026_10_18_dsx01_receiver_phase/DSX01-S01/shared_phase/endpoints.json"
    for key, fit in json.loads(p.read_text()).items():
        variant, arm = key.split("/")
        factor = float(variant.rsplit("_", 1)[1])
        yield (
            "phase",
            variant,
            arm,
            fit,
            lambda *args, s=factor: phase_problem(
                *args, mean_sigma=10, height_sigma=0, phase_factor=s
            ),
        )
    p = base / "2026_10_18_dsx01_receiver_identity/DSX01-S01/shared_phase/mean_10_iterations.json"
    for r in json.loads(p.read_text()):
        for arm, fit in r["fits"].items():
            yield (
                "identity",
                f"round{r['iteration']}",
                arm,
                fit,
                lambda *args: geometry_problem(*args, mean_sigma=10, height_sigma=0),
            )
    for aligned in (False, True):
        p = base / "2026_10_18_dsx01_mean_motion"
        if aligned:
            p = p / "reference_aligned"
        p = p / "DSX01-S01/shared_phase/endpoints.json"
        for key, fit in json.loads(p.read_text()).items():
            variant, arm = key.split("/")
            sigma = float(variant.rsplit("_", 1)[1])

            def factory(*args, s=sigma, ref=aligned):
                if not s:
                    return geometry_problem(*args, mean_sigma=10, height_sigma=0)
                return ReceiverDriftProblem(
                    MotionFamilies(
                        *args, sigma=s, basis_provider=reference_motion_basis if ref else None
                    ),
                    mean_sigma=10,
                )

            yield "reference_motion" if aligned else "epoch_motion", variant, arm, fit, factory
    p = base / "2026_10_18_dsx01_receiver_consensus/DSX01-S01/shared_phase/endpoints.json"
    for arm, fit in json.loads(p.read_text()).items():
        yield (
            "consensus",
            "bounded_family",
            arm,
            fit,
            lambda *args: ReceiverDriftProblem(
                ConsensusFamilies(*args, mode="consensus_floor"), mean_sigma=10
            ),
        )


def run():
    scan = Scan("DSX01-S01")
    summary, metrics = [], {}
    for experiment, variant, arm, fit, factory in inputs():
        item = dict(experiment=experiment, variant=variant, arm=arm, method="shared_phase", fit=fit)
        metric = nominated_metrics(scan, item, problem_factory=factory)
        metrics[experiment, variant, arm] = metric
        summary.append(
            dict(
                experiment=experiment,
                variant=variant,
                arm=arm,
                position_error_km=distance_km(
                    (fit["latitude_deg"], fit["longitude_deg"]), REFERENCE
                ),
                frequency_prior_score=fit["frequency_prior_score"],
                complexity_penalty=fit["complexity_penalty"],
                total_score=fit["score"],
                **{k: v for k, v in metric.items() if k != "tracks"},
            )
        )
    comparisons = []
    for experiment, variant, arm in metrics:
        if arm != "c0":
            continue
        rr = [
            {
                r["component"]: r
                for r in metrics[experiment, variant, a]["tracks"]
                if r["compatible"]
            }
            for a in ("c0", "fitted_c")
        ]
        common = rr[0].keys() & rr[1].keys()
        n = sum(rr[0][k]["points"] for k in common)
        row = dict(
            experiment=experiment,
            variant=variant,
            common_accepted_points=n,
            same_label_points=sum(
                rr[0][k]["points"] for k in common if rr[0][k]["norad"] == rr[1][k]["norad"]
            ),
        )
        for a, r in zip(("c0", "fitted_c"), rr, strict=True):
            row[f"native_rms_{a}_hz"] = float(
                np.sqrt(sum(r[k]["native_square_hz2"] for k in common) / max(1, n))
            )
            row[f"innovation_rms_{a}_hz"] = float(
                np.sqrt(sum(r[k]["innovation_square_hz2"] for k in common) / max(1, n))
            )
        comparisons.append(row)
    for name, rows in [
        ("supplementary_controls", summary),
        ("supplementary_c_ablation", comparisons),
    ]:
        write(OUTPUT / f"{name}.json", rows)
        with (OUTPUT / f"{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return summary


if __name__ == "__main__":
    run()
