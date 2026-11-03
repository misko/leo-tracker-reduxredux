"""Blind curved-family support and nuisance-prior ablations on a fixed grid."""

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import CENTER, GRID, OUTPUT, FixedFamilies, latlon

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

VARIANTS = ("supported_families", "weak_phase", "wide_drift", "supported_weak_phase")


def modified_problem(problem, variant):
    """Fix support from blind nominations, then make one continuous objective."""
    p = problem
    lower, upper = np.array(p.lower), np.array(p.upper)
    receiver_channels = defaultdict(set)
    for i, row in zip(p.members, p.rows, strict=True):
        t = p.scan.tracks[i]
        receiver_channels[row["candidate_index"]].add((t["receiver"], t["channel"]))
    supported = {j for j, channels in receiver_channels.items() if len(channels) >= 2}
    weights = np.ones(len(p.residual(p.initial)))
    offset, included = 0, []
    for i, row in zip(p.members, p.rows, strict=True):
        n = len(p.scan.tracks[i]["times"])
        parts = 2 if p.method == "penalized_split" and row["split_at"] > 0 else 1
        size = 2 * n + parts
        take = not variant.startswith("supported") or row["candidate_index"] in supported
        if not take:
            weights[offset : offset + size] = 0
        else:
            included.append(row["component"])
        offset += size
    assert len(weights) - offset == 4 + len(p.labels) + sum(
        1 if p.method == "family_rate" else 2 for _ in p.extra_labels
    ) + (p.starts["smooth"].size if p.method == "receiver_smooth" else 0)
    if "weak_phase" in variant:
        weights[offset + 4 : offset + 4 + len(p.labels)] /= 3
    if variant == "wide_drift":
        weights[offset : offset + 4] /= 4
        for k, (key, scale) in enumerate(p.coordinates):
            if key[0] == "beta" and 4 <= key[1] < 8:
                lower[k], upper[k] = -750 / scale, 750 / scale
    return (
        lambda x: p.residual(x) * weights,
        lower,
        upper,
        dict(
            included_curved_tracks=included,
            omitted_from_geographic_objective=[
                r["component"] for r in p.rows if r["component"] not in included
            ],
            supported_norads=[int(p.scan.norads[j]) for j in sorted(supported)],
            phase_sigma_multiplier=3 if "weak_phase" in variant else 1,
            drift_sigma_hz_s=2 if variant == "wide_drift" else 0.5,
            drift_bound_hz_s=5 if variant == "wide_drift" else 1,
        ),
    )


def run(case, methods=METHODS, variants=VARIANTS):
    directory = OUTPUT / case / "support_ablation"
    directory.mkdir(exist_ok=True)
    scan = Scan(case)
    seeds = json.loads((OUTPUT / case / "mill_valley_center_seeds.json").read_text())
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_evaluation_GPS_used=True,
            center=CENTER,
            grid=GRID,
            max_iterations=24,
            starts=3,
            c_arms_same_observations_candidates_support_mask_other_priors_and_search_budgets=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            variants=variants,
            methods=methods,
            supported_rule=(
                "at least two distinct (receiver,channel) curved nominations at blind center"
            ),
            unsupported_tracks_remain_available_for_postfit_association=True,
            priors_are_sensitivity_probes_not_validated_uncertainty_models=True,
        ),
    )
    for method in methods:
        for variant in variants:
            if all(f"{variant}/{arm}/{method}" in results for arm in ("c0", "fitted_c")):
                continue
            problems, grid = {}, []
            for arm in ("c0", "fitted_c"):
                p = FixedFamilies(
                    scan, seeds[f"c0/{method}"], method, "continuous", arm == "fitted_c"
                )
                problems[arm] = (p, *modified_problem(p, variant))
            for point in GRID:
                row = dict(east_north_km=point, scores={})
                for arm, (p, f, _lo, _hi, _mask) in problems.items():
                    x = p.initial.copy()
                    x[:2] = point
                    r = f(x)
                    row["scores"][arm] = float(r @ r)
                grid.append(row)
            selected = sorted(grid, key=lambda r: r["scores"]["c0"])[:3]
            for arm, (p, f, lo, hi, mask) in problems.items():
                mark, fits = time.monotonic(), []
                for row in selected:
                    x = p.initial.copy()
                    x[:2] = row["east_north_km"]
                    fit = bounded_gauss_newton(f, x, lo, hi, iterations=24)
                    fit["start_east_north_km"] = row["east_north_km"]
                    fits.append(fit)
                best = min(fits, key=lambda r: r["score"])
                x = best["parameters"]
                key = f"{variant}/{arm}/{method}"
                results[key] = dict(
                    latitude_deg=latlon(x[:2])[0],
                    longitude_deg=latlon(x[:2])[1],
                    east_north_km=x[:2],
                    score=best["score"],
                    fits=fits,
                    grid=grid,
                    mask=mask,
                    state=p.decode(x),
                    elapsed_seconds=time.monotonic() - mark,
                )
                write(output, results)
                print(
                    json.dumps(
                        dict(
                            case=case,
                            key=key,
                            xy=list(x[:2]),
                            score=best["score"],
                            seconds=time.monotonic() - mark,
                        )
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
    args = parser.parse_args()
    run(args.case, methods=tuple(args.methods), variants=tuple(args.variants))
