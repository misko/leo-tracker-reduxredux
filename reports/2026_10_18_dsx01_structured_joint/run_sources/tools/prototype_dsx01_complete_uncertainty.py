"""Combine nonlinear RX dynamics with all five non-phase orbital directions."""

import argparse
import json

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from build_dsx01_orbit_modes import build_modes
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import fit_once
from prototype_dsx01_orbit_marginal import MarginalFamilies
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem


def complete_modes(scan, labels, supported):
    cache_key = tuple(labels), tuple(supported)
    if not hasattr(scan, "complete_uncertainty_cache"):
        scan.complete_uncertainty_cache = {}
    if cache_key in scan.complete_uncertainty_cache:
        return scan.complete_uncertainty_cache[cache_key]
    bank, metadata = build_modes(scan, labels, supported, "physical")
    dp = bank["position_km"].reshape(len(labels), 3, -1, 3)
    dv = bank["velocity_km_s"].reshape(len(labels), 3, -1, 3)
    shape = (len(labels), 5, *dp.shape[2:])
    pp, vv = np.zeros(shape), np.zeros(shape)
    pp[:, :3], vv[:, :3] = dp, dv
    metadata = {j: dict(row) for j, row in metadata.items()}
    for k, j in enumerate(labels):
        if j not in supported:
            continue
        a, b = scan.element_basis(j)
        pp[k, 3:], vv[k, 3:] = 1e-4 * a, 1e-4 * b
        metadata[j]["eccentricity_vector_sigma"] = 1e-4
    result = (
        dict(
            time_s=bank["time_s"],
            position_km=pp.reshape(-1, *pp.shape[2:]),
            velocity_km_s=vv.reshape(-1, *vv.shape[2:]),
        ),
        metadata,
    )
    scan.complete_uncertainty_cache[cache_key] = result
    return result


def complete_problem(*args, likelihood="student", scale=1.0):
    scan, seed, method, fitted_c, anchor = args
    active = [r for r in seed["rows"] if r["active_curvature"]]
    labels = sorted({r["candidate_index"] for r in active})
    index = {t["key"]: t for t in scan.tracks}
    supported = [
        j
        for j in labels
        if len(
            {
                (index[r["component"]]["receiver"], index[r["component"]]["channel"])
                for r in active
                if r["candidate_index"] == j
            }
        )
        >= 2
    ]
    p = MarginalFamilies(
        *args,
        kind="physical",
        likelihood=likelihood,
        scale=scale,
        provided_modes=complete_modes(scan, labels, supported),
    )
    return ReceiverDriftProblem(p, mean_sigma=10)


def run(case, method, *, refreshed=False, variants=("student_1", "gaussian_1", "student_3")):
    directory = (
        OUTPUT / "complete_uncertainty" / case / method / ("refreshed" if refreshed else "original")
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    if refreshed:
        source = (
            OUTPUT.parent
            / "2026_10_18_dsx01_receiver_identity"
            / case
            / method
            / "mean_10_endpoints.json"
        )
        seed = json.loads(source.read_text())["c0"]
        anchor = seed["east_north_km"]
    else:
        source = SOURCE / case / f"{method}_center.json"
        seed, anchor = json.loads(source.read_text()), (0, 0)
    scan = Scan(case)
    # Both original and refreshed identities are derived without GPS. Every
    # variant keeps the exact c0 candidate inventory, observation IDs and aliases.
    nominal = complete_problem(scan, seed, method, False, anchor)
    locked = seed.get("aliases", nominal.alias)
    write(
        directory / "protocol.json",
        dict(
            blind_source=str(source),
            inherited_completed_blind_grid=refreshed,
            no_GPS_or_future_elements=True,
            variants=list(variants),
            common_c0_aliases_rows_starts_and_24_iteration_budgets=True,
            physical_modes=[
                "reference_mean_motion",
                "inclination",
                "RAAN",
                "e_cos_omega",
                "e_sin_omega",
            ],
            eccentricity_vector_sigma=1e-4,
            scales_are_fixed_engineering_controls_not_GPS_tuned=True,
            physical_scale_selection_if_used_is_c0_marginal_objective_only=True,
        ),
    )
    for variant in variants:
        if all(f"{variant}/{a}" in results for a in ("c0", "fitted_c")):
            continue
        likelihood, scale = variant.split("_")

        def factory(*args, ll=likelihood, s=float(scale)):
            p = complete_problem(*args, likelihood=ll, scale=s)
            p.problem.alias = list(locked)
            return p

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        for arm, fit in fits.items():
            results[f"{variant}/{arm}"] = fit
        write(path, results)
        print(
            case,
            method,
            refreshed,
            variant,
            {a: f["east_north_km"] for a, f in fits.items()},
            flush=True,
        )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, default="receiver_smooth")
    p.add_argument("--refreshed", action="store_true")
    p.add_argument("--variants", nargs="+", default=["student_1", "gaussian_1", "student_3"])
    a = p.parse_args()
    run(a.case, a.method, refreshed=a.refreshed, variants=a.variants)
