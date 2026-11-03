"""Test the phase-prior interaction after releasing common receiver drift."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import fit_once
from prototype_dsx01_receiver_geometry import OUTPUT as SOURCE
from prototype_dsx01_receiver_geometry import SOURCE as SEEDS
from prototype_dsx01_receiver_geometry import geometry_problem

OUTPUT = ROOT / "reports/2026_10_18_dsx01_receiver_phase"


class PhaseScaleProblem:
    """Scale only existing per-satellite phase priors, retaining finite bounds."""

    def __init__(self, problem, factor=3.0):
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError("positive finite phase-prior scale required")
        self.problem, self.factor = problem, factor
        tail = getattr(problem, "altitude_parameters", 0)
        tail += len(getattr(problem, "shape_labels", []))
        tail += sum(1 if problem.method == "family_rate" else 2 for _ in problem.extra_labels)
        if problem.method == "receiver_smooth":
            tail += problem.starts["smooth"].size
        end = len(problem.residual(problem.initial)) - tail
        self.phase_slice = slice(end - len(problem.labels), end)

    def __getattr__(self, name):
        return getattr(self.problem, name)

    def residual(self, x, *, details=False):
        result = self.problem.residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        r[self.phase_slice] /= self.factor
        return (r, diagnostics) if details else r


def phase_problem(*args, mean_sigma, height_sigma, phase_factor):
    return PhaseScaleProblem(
        geometry_problem(*args, mean_sigma=mean_sigma, height_sigma=height_sigma),
        factor=phase_factor,
    )


def run(case, method, *, mean=10.0, height=0.0, factors=(1.0, 3.0, 10.0)):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    seed_path = SEEDS / case / f"{method}_center.json"
    seed = json.loads(seed_path.read_text())
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_states=True,
            mean_drift_sigma_hz_s=mean,
            height_sigma_m=height,
            phase_factors=factors,
            unchanged_phase_bounds_s=[-15, 15],
            other_priors_points_candidates_geographic_starts_and_24_iteration_budgets_match_c_arms=True,
            seed_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    scan = None
    for factor in factors:
        name = f"mean_{mean:g}_height_{height:g}_phase_{factor:g}"
        if all(f"{name}/{arm}" in results for arm in ("c0", "fitted_c")):
            continue
        if factor == 1:
            previous = SOURCE / case / method / "endpoints.json"
            data = json.loads(previous.read_text()) if previous.exists() else {}
            key = f"mean_{mean:g}_height_{height:g}"
            if all(f"{key}/{arm}" in data for arm in ("c0", "fitted_c")):
                for arm in ("c0", "fitted_c"):
                    results[f"{name}/{arm}"] = dict(
                        data[f"{key}/{arm}"],
                        reused_from=str(previous.relative_to(ROOT)) + "/" + key,
                    )
                write(path, results)
                continue
        scan = Scan(case) if scan is None else scan

        def factory(*args, scale=factor):
            return phase_problem(*args, mean_sigma=mean, height_sigma=height, phase_factor=scale)

        fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
        for arm, fit in fits.items():
            results[f"{name}/{arm}"] = fit
        write(path, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    variant=name,
                    positions={a: f["east_north_km"].tolist() for a, f in fits.items()},
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S01")
    parser.add_argument("--method", choices=METHODS, default="shared_phase")
    parser.add_argument("--mean", type=float, default=10.0)
    parser.add_argument("--height", type=float, default=0.0)
    a = parser.parse_args()
    run(a.case, a.method, mean=a.mean, height=a.height)
