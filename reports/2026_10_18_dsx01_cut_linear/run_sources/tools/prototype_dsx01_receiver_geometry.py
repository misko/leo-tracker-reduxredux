"""Matched common-RX drift and unknown-height controls across DSX01.

Only original curved fragments calibrate and locate. The nominal town grid
does not use evaluation GPS; receiver height starts at zero, with a declared
Gaussian prior and finite physical bounds, rather than a known-site value.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_continuous_position import CENTER, GRID
from prototype_s01_receiver_drift import ReceiverDriftProblem

OUTPUT = ROOT / "reports/2026_10_18_dsx01_receiver_geometry"
SOURCE = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32"
PREVIOUS = ROOT / "reports/2026_10_18_s01_receiver_drift"


class HeightFamilies(AnchoredFamilies):
    """One geodetic receiver height, shared by every receiver and candidate."""

    def __init__(self, scan, seed, method, fitted_c, anchor, *, sigma=500.0):
        if not np.isfinite(sigma) or sigma <= 0:
            raise ValueError("positive finite receiver height scale required")
        self.base_size = None
        self.altitude_parameters, self.height_sigma = 1, sigma
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.base_size = len(self.initial)
        self.initial = np.r_[self.initial, 0.0]
        self.lower = np.r_[self.lower, -100.0 / sigma]
        self.upper = np.r_[self.upper, 1500.0 / sigma]

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["altitude_m"] = float(x[-1] * self.height_sigma)
        return state

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        return (np.r_[result[0], x[-1]], result[1]) if details else np.r_[result, x[-1]]


def geometry_problem(scan, seed, method, fitted_c, anchor, *, mean_sigma, height_sigma):
    problem = (
        HeightFamilies(scan, seed, method, fitted_c, anchor, sigma=height_sigma)
        if height_sigma
        else AnchoredFamilies(scan, seed, method, fitted_c, anchor)
    )
    if mean_sigma:
        problem = ReceiverDriftProblem(problem, mean_sigma=mean_sigma)
    return problem


def run(case, method, *, means=(5.0, 10.0), heights=(0.0,), iterations=24):
    if any(not np.isfinite(v) or v < 0 for v in (*means, *heights)):
        raise ValueError("finite nonnegative sensitivity scales required")
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    seed_path = SOURCE / case / f"{method}_center.json"
    seed = json.loads(seed_path.read_text())
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    protocol_path = directory / "protocol.json"
    protocol = json.loads(protocol_path.read_text()) if protocol_path.exists() else {}
    variants = set(protocol.get("requested_variants", []))
    variants.update(f"mean_{m:g}_height_{h:g}" for m in means for h in heights)
    write(
        protocol_path,
        dict(
            case=case,
            method=method,
            center=CENTER,
            grid=GRID,
            requested_variants=sorted(variants),
            max_iterations=iterations,
            mean_sigma_zero_means_original_band_drift_prior=True,
            height_sigma_zero_means_fixed_zero_height=True,
            band_contrast_sigma_hz_s=0.5,
            height_bounds_m=[-100, 1500],
            height_prior_mean_m=0.0,
            aliases_and_nomination_from_blind_center=True,
            no_reference_GPS_or_oracle_initialization=True,
            original_curved_population_only=True,
            matched_c0_fitted_c_same_data_candidates_priors_starts_and_budgets=True,
            seed_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            sources_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    ROOT / "tools/prototype_s01_receiver_drift.py",
                    ROOT / "tools/prototype_dsx01_continuous_position.py",
                    ROOT / "src/leo/analysis/research/continuous_curve_fit.py",
                )
            },
        ),
    )
    scan = None
    for mean in means:
        for height in heights:
            name = f"mean_{mean:g}_height_{height:g}"
            if all(f"{name}/{arm}" in results for arm in ("c0", "fitted_c")):
                continue
            previous_path = PREVIOUS / method / "endpoints.json"
            if case == "DSX01-S01" and not height and previous_path.exists() and iterations == 24:
                previous = json.loads(previous_path.read_text())
                old_name = f"rx_mean_{mean:g}_shape_0"
                if all(f"{old_name}/{arm}" in previous for arm in ("c0", "fitted_c")):
                    for arm in ("c0", "fitted_c"):
                        results[f"{name}/{arm}"] = dict(
                            previous[f"{old_name}/{arm}"],
                            reused_from=str(previous_path.relative_to(ROOT)) + "/" + old_name,
                            reused_source_sha256=hashlib.sha256(
                                previous_path.read_bytes()
                            ).hexdigest(),
                        )
                    write(path, results)
                    continue
            if scan is None:
                scan = Scan(case)

            def factory(scan, seed, method, fitted_c, anchor, ms=mean, hs=height):
                return geometry_problem(
                    scan, seed, method, fitted_c, anchor, mean_sigma=ms, height_sigma=hs
                )

            fits = fit_once(
                scan, seed, method, (0.0, 0.0), iterations=iterations, problem_class=factory
            )
            for arm, fit in fits.items():
                results[f"{name}/{arm}"] = fit
            write(path, results)
            print(
                json.dumps(
                    dict(
                        case=case,
                        method=method,
                        variant=name,
                        positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                        height_m={arm: f["state"].get("altitude_m", 0) for arm, f in fits.items()},
                        drift_hz_s={
                            arm: list(f["state"]["beta"][4:8] / 150) for arm, f in fits.items()
                        },
                    )
                ),
                flush=True,
            )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=[f"DSX01-S0{k}" for k in range(1, 6)], required=True)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--means", type=float, nargs="+", default=(5.0, 10.0))
    parser.add_argument("--heights", type=float, nargs="+", default=(0.0,))
    args = parser.parse_args()
    run(args.case, args.method, means=tuple(args.means), heights=tuple(args.heights))
