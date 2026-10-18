"""Renominate linear geometry from the fresh curved-only c0 fit, then map it."""

import argparse
import json
import time

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import actual_metrics
from dsx01_cut_linear import bounded_scalar_newton, curve_posterior, transfer_design
from dsx01_inference_audit import InferenceReadGuard, disk_grid
from dsx01_smooth_background import background_logprob
from map_dsx01_clean_region import factory, finite_gradient
from probe_dsx01_cut_linear import CutScore, dense_cost
from prototype_dsx01_continuous_position import GRID, latlon
from report_dsx01_cut_linear import linear_metrics
from run_dsx01_clean_region import OUTPUT, load_scan

from leo.analysis.research.retained_track_likelihood import PERIOD

VARIANTS = ("joint", "shape", "continuation", "white_joint", "white_shape")


def nominations_for(p, point, metrics):
    scan = p.scan
    owners, groups, anchors = {}, set(), {}
    for row, i in zip(metrics["tracks"], p.members, strict=True):
        t, j = scan.tracks[i], row["candidate_index"]
        if row["compatible"]:
            owners.setdefault(j, set()).add((t["receiver"], t["channel"]))
            groups.add((t["receiver"], t["channel"] > 4))
            anchors.setdefault(j, []).append(t)
    candidates = sorted(j for j in owners if len(owners[j]) >= 2 and j in p.supported)
    result, root = curve_posterior(p, point)
    nominations = []
    for i, t in enumerate(scan.tracks):
        if i in scan.curved or len(t["times"]) < 6 or np.ptp(t["times"]) <= 0:
            continue
        choices = []
        for j in candidates if (t["receiver"], t["channel"] > 4) in groups else []:
            intercept, design, elevation = transfer_design(p, t, j, point)
            if elevation.min() < 0:
                continue
            alias = int(
                np.rint(np.mean(intercept + design @ result["coefficient"] - t["values"]) / PERIOD)
            )
            raw = t["values"] + alias * PERIOD - intercept
            cost = dense_cost(raw, design, result["coefficient"], root, 1000)
            same = [
                a
                for a in anchors[j]
                if (a["receiver"], a["channel"]) == (t["receiver"], t["channel"])
            ]
            gap = min(
                (
                    max(
                        0.0,
                        float(t["times"].min() - a["times"].max()),
                        float(a["times"].min() - t["times"].max()),
                    )
                    for a in same
                ),
                default=float("inf"),
            )
            choices.append(
                dict(
                    candidate_index=j,
                    norad=int(scan.norads[j]),
                    alias=alias,
                    cost=cost,
                    same_channel_gap_s=gap if np.isfinite(gap) else None,
                )
            )
        choices.sort(key=lambda r: r["cost"])
        background = background_logprob(t["values"], t["times"], 150.0)["log_probability"]
        best, accepted = {}, False
        if choices:
            best = choices[0]
            odds = (
                np.log(0.95 / 0.05)
                - best["cost"] / 2
                - np.log(max(1, len(candidates)))
                - background
            )
            margin = (choices[1]["cost"] - best["cost"]) / 2 if len(choices) > 1 else float("inf")
            accepted = bool(odds >= np.log(99) and margin >= np.log(10))
        nominations.append(
            dict(index=i, component=t["key"], points=len(t["times"]), accepted=accepted, **best)
        )
    return nominations


def run(case):
    directory = OUTPUT / case
    guard = InferenceReadGuard(OUTPUT)
    guard.install()
    source = json.loads((directory / "surfaces/normal/result.json").read_text())
    scan, sigma = load_scan(case)
    node = source["selected_assignment_node"]
    problems = {
        a: factory(scan, node, sigma, "normal", a == "fitted_c", reference=r["phase_reference_s"])
        for a, r in source["arms"].items()
    }
    parent = source["arms"]["c0"]["fit"]
    point = np.array(parent["parameters"])
    fit = dict(
        parent,
        rows=problems["c0"].rows,
        aliases=problems["c0"].alias,
        east_north_km=point,
        fits=[parent],
    )
    metrics = actual_metrics(problems["c0"], fit, "c0", point)
    nominations = nominations_for(problems["c0"], point, metrics)
    candidates = [n for n in nominations if n["accepted"]]
    strict = {
        r["component"] for r in linear_metrics(problems["c0"], point, candidates) if r["compatible"]
    }
    write(
        directory / "fresh_linear_nominations.json",
        dict(nominations=nominations, strict_components=sorted(strict), curved_metrics=metrics),
    )
    axis, points = disk_grid(step_km=2.0)
    for variant in VARIANTS:
        path = directory / "surfaces" / f"linear_{variant}" / "result.json"
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        mark = time.monotonic()
        selected = [
            dict(
                n,
                accepted=n["accepted"]
                and (not variant.startswith("white") or n["component"] in strict),
            )
            for n in nominations
        ]
        kind = (
            "shape"
            if variant.endswith("shape")
            else "joint"
            if variant.startswith("white")
            else variant
        )
        scores = {a: CutScore(p, selected, kind) for a, p in problems.items()}
        functions = {a: (lambda x, s=s: s.score(x)["total"]) for a, s in scores.items()}
        grid = [dict(point=x, score=functions["c0"](x)) for x in [*GRID, point]]
        starts = sorted(grid, key=lambda r: r["score"])[:3]
        arms = {}
        for arm, function in functions.items():
            attempts = [bounded_scalar_newton(function, s["point"]) for s in starts]
            best = min(attempts, key=lambda r: r["score"])
            values = [function(x) for x in points]
            probes = [
                bounded_scalar_newton(function, s)
                for s in [[0, 0], *[points[i] for i in np.argsort(values)[:2]]]
            ]
            residual = problems[arm].calculate(best["parameters"])["conditional_residual_hz"]
            arms[arm] = dict(
                fit=dict(best, attempts=attempts),
                map_points=points,
                loss=values,
                multistart_probes=probes,
                endpoint_latlon=latlon(best["parameters"]),
                gradient_at_center=finite_gradient(function, [0, 0]),
                gradient_at_endpoint=finite_gradient(function, best["parameters"]),
                residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
                linear_points=sum(n["points"] for n in scores[arm].selected),
            )
        write(
            path,
            dict(
                case=case,
                method=f"linear_{variant}",
                arms=arms,
                axis=axis,
                seconds=time.monotonic() - mark,
                conditional_assignment=True,
                GPS_or_following_TLE_used=False,
                actual_report_inputs_read=sorted(guard.read_paths),
                calibration_from_curves_only=True,
                linear_nominations_from_fresh_same_scan_c0=True,
            ),
        )
        print(case, variant, round(time.monotonic() - mark, 1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    run(parser.parse_args().case)
