"""Blind static-site factors with independent scan hardware and causal orbits."""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import CENTER, GRID, OUTPUT, FixedFamilies

from leo.analysis.research.factor_position_fit import factor_gauss_newton

POOLS = ("independent_phase", "shared_tle")


class Pool:
    def __init__(self, scans, seeds, method, arm, pool, variant="continuous"):
        self.problems = [
            FixedFamilies(s, seed[f"c0/{method}"], method, variant, arm == "fitted_c")
            for s, seed in zip(scans, seeds, strict=True)
        ]
        self.names, lookup, self.mappings = [], {}, []
        values, lower, upper = [], [], []
        for p in self.problems:
            indexes = []
            for k, ((key, _scale), value, lo, hi) in enumerate(
                zip(p.coordinates, p.initial, p.lower, p.upper, strict=True)
            ):
                name = ("position", k) if k < 2 else ("scan", p.scan.case, *key)
                if pool == "shared_tle" and (
                    key[0] == "phases" or (key[0] == "extra" and method == "orbit_em")
                ):
                    norad = str(int(p.scan.norads[key[1]]))
                    lines = p.scan.elements[norad]["lines"]
                    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
                    name = (key[0], norad, digest, *key[2:])
                if name not in lookup:
                    lookup[name] = len(self.names)
                    self.names.append(name)
                    values.append([])
                    lower.append(lo)
                    upper.append(hi)
                index = lookup[name]
                values[index].append(float(value))
                lower[index], upper[index] = max(lower[index], lo), min(upper[index], hi)
                indexes.append(index)
            self.mappings.append(indexes)
        self.initial = np.array([np.median(v) for v in values])
        self.lower, self.upper = np.array(lower), np.array(upper)
        occurrences = Counter(i for m in self.mappings for i in m)
        canonical_sigma = {}
        for p, m in zip(self.problems, self.mappings, strict=True):
            for index, (key, _scale) in zip(m, p.coordinates, strict=True):
                if key[0] == "phases":
                    canonical_sigma[index] = max(
                        canonical_sigma.get(index, 0), p.scan.sigma[key[1]]
                    )
        self.functions = []
        for p, m in zip(self.problems, self.mappings, strict=True):
            # Data/receiver priors stay separate. A shared TLE parameter's
            # Gaussian prior is charged once across all factors using it.
            extra_count = sum(1 if method == "family_rate" else 2 for _ in p.extra_labels)
            smooth_count = p.starts["smooth"].size if method == "receiver_smooth" else 0
            trailing = len(p.labels) + extra_count + smooth_count
            sample = p.residual(p.initial)
            phase_start = len(sample) - trailing
            weights = np.ones(len(sample))
            coord_to_index = {
                tuple(key): index for index, (key, _scale) in zip(m, p.coordinates, strict=True)
            }
            for k, j in enumerate(p.labels):
                index = coord_to_index["phases", j]
                weights[phase_start + k] = p.scan.sigma[j] / (
                    canonical_sigma[index] * np.sqrt(occurrences[index])
                )
            k = phase_start + len(p.labels)
            for j in p.extra_labels:
                for coordinate in range(1 if method == "family_rate" else 2):
                    index = coord_to_index["extra", j, coordinate]
                    weights[k] = 1 / np.sqrt(occurrences[index])
                    k += 1
            self.functions.append(lambda x, problem=p, w=weights: problem.residual(x) * w)
        self.shared_parameters = [
            dict(name=name, occurrences=occurrences[k])
            for k, name in enumerate(self.names)
            if occurrences[k] > 1 and k >= 2
        ]

    def score(self, parameters):
        return sum(
            float((r := f(parameters[m])) @ r)
            for f, m in zip(self.functions, self.mappings, strict=True)
        )


def run(*, methods=METHODS, pools=POOLS, iterations=24, starts=3):
    directory = OUTPUT / "pooled"
    directory.mkdir(exist_ok=True)
    scans = [Scan(f"DSX01-S0{k}") for k in range(1, 6)]
    seeds = [
        json.loads((OUTPUT / s.case / "mill_valley_center_seeds.json").read_text()) for s in scans
    ]
    write(
        directory / "protocol.json",
        dict(
            region_center=CENTER,
            region_box_km=[[-12.5, 12.5]] * 2,
            grid_east_north_km=GRID,
            no_evaluation_GPS_in_fit=True,
            hardware_separate_for_each_scan_RX_and_band=True,
            shared_orbit_only_when_full_causal_TLE_lines_identical=True,
            phase_and_orbit_prior_charged_once_per_shared_TLE_parameter=True,
            candidate_labels_fixed_from_blind_center=True,
            objective="continuous robust curved frequency fit",
            pools=pools,
            methods=methods,
            refined_starts=starts,
            max_iterations=iterations,
            c_arms_same_observations_labels_priors_grid_and_iteration_budgets=True,
            exact_duplicate_parameterizations_reuse_identical_numerical_result=True,
            stationary_receiver_site_assumption=True,
            no_verified_identity_claim=True,
            source_sha256={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    Path(__file__).with_name("prototype_dsx01_continuous_position.py"),
                    Path(__file__).parents[1] / "src/leo/analysis/research/factor_position_fit.py",
                )
            },
            seed_sha256={
                s.case: hashlib.sha256(
                    (OUTPUT / s.case / "mill_valley_center_seeds.json").read_bytes()
                ).hexdigest()
                for s in scans
            },
        ),
    )
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    for method in methods:
        for pool_name in pools:
            if all(f"{pool_name}/{arm}/{method}" in results for arm in ("c0", "fitted_c")):
                continue
            problems = {
                arm: Pool(scans, seeds, method, arm, pool_name) for arm in ("c0", "fitted_c")
            }
            if pool_name == "shared_tle" and all(
                not p.shared_parameters for p in problems.values()
            ):
                # With no repeated observed satellite/TLE pair there is no
                # parameter to share: this factor graph is exactly the control.
                for arm in problems:
                    original_key = f"independent_phase/{arm}/{method}"
                    results[f"{pool_name}/{arm}/{method}"] = dict(
                        results[original_key],
                        numerical_equivalent_to=original_key,
                        equivalence_reason="no observed satellite/full-TLE pair repeats",
                        elapsed_seconds=0.0,
                    )
                write(output, results)
                print(
                    json.dumps(dict(method=method, shared_tle_exactly_equals_independent=True)),
                    flush=True,
                )
                continue
            grid = []
            for point in GRID:
                row = dict(east_north_km=point, scores={})
                for arm, p in problems.items():
                    x = p.initial.copy()
                    x[:2] = point
                    row["scores"][arm] = p.score(x)
                grid.append(row)
            selected = sorted(grid, key=lambda r: r["scores"]["c0"])[:starts]
            for arm, p in problems.items():
                mark, fits = time.monotonic(), []
                for row in selected:
                    x = p.initial.copy()
                    x[:2] = row["east_north_km"]
                    fit = factor_gauss_newton(
                        p.functions, p.mappings, x, p.lower, p.upper, iterations=iterations
                    )
                    fit["start_east_north_km"] = row["east_north_km"]
                    fits.append(fit)
                best = min(fits, key=lambda r: r["score"])
                x = best["parameters"]
                point = x[:2]
                latitude = CENTER[0] + point[1] / 111
                longitude = CENTER[1] + point[0] / (111.32 * np.cos(np.deg2rad(CENTER[0])))
                key = f"{pool_name}/{arm}/{method}"
                results[key] = dict(
                    latitude_deg=latitude,
                    longitude_deg=longitude,
                    east_north_km=point,
                    score=best["score"],
                    grid=grid,
                    starts=selected,
                    fits=fits,
                    shared_parameters=p.shared_parameters,
                    states={
                        problem.scan.case: problem.decode(x[m])
                        for problem, m in zip(p.problems, p.mappings, strict=True)
                    },
                    elapsed_seconds=time.monotonic() - mark,
                )
                write(output, results)
                print(
                    json.dumps(
                        dict(
                            key=key,
                            position=list(point),
                            score=best["score"],
                            shared=len(p.shared_parameters),
                            seconds=time.monotonic() - mark,
                        )
                    ),
                    flush=True,
                )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    parser.add_argument("--pools", nargs="+", choices=POOLS, default=POOLS)
    parser.add_argument("--iterations", type=int, default=24)
    parser.add_argument("--starts", type=int, default=3)
    args = parser.parse_args()
    run(
        methods=tuple(args.methods),
        pools=tuple(args.pools),
        iterations=args.iterations,
        starts=args.starts,
    )
