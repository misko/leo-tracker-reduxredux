"""Following-element sensitivity only; these future states are never a causal solution."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from iterate_dsx01_position_nominations import fit_once
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_receiver_geometry import SOURCE, geometry_problem
from sgp4.api import Satrec

from leo.sky.propagation import ElementSetCatalogue


def run(case):
    directory = OUTPUT / "following_diagnostic" / case
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source = OUTPUT / "orbit_history_and_following_diagnostic.json"
    data = json.loads(source.read_text())[case]
    seed_path = SOURCE / case / "shared_phase_center.json"
    seed = json.loads(seed_path.read_text())
    seed["state"]["phases"] = np.zeros(len(seed["state"]["phases"]))
    scan = Scan(case)
    original = {k: v.copy() for k, v in scan.sky.items()}
    locked = geometry_problem(
        scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0
    ).alias
    numbers = sorted({r["candidate_norad"] for r in seed["rows"]})
    following = {n: data["candidates"][str(n)]["first_following_newer_version"] for n in numbers}
    following = {n: r for n, r in following.items() if r is not None}
    nums = tuple(following)
    cat = ElementSetCatalogue(
        tuple(map(str, nums)), nums, tuple(Satrec.twoline2rv(*following[n]["lines"]) for n in nums)
    )
    p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
    if not good.all():
        raise ValueError("following diagnostic propagation failed")
    indexes = [int(np.flatnonzero(scan.norads == n)[0]) for n in nums]
    write(
        directory / "protocol.json",
        dict(
            future_elements_diagnostic_only_not_a_causal_localization_result=True,
            supplied_GPS_never_read_by_fitter=True,
            causal_candidate_inventory_and_nominations_unchanged=True,
            no_candidate_deletion_for_missing_following_versions=True,
            nominated_candidates=len(numbers),
            following_version_count=len(nums),
            initial_phases_reset_zero_in_both_TLE_variants=True,
            same_causal_center_hardware_seed_and_fixed_aliases=True,
            same_grid_procedure_3_starts_24_iterations_in_both_TLE_variants=True,
            common_c0_actual_geographic_starts_for_c_arms=True,
            original_causal_phase_priors_unchanged=True,
            input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            following_versions={str(n): r for n, r in following.items()},
        ),
    )
    for version in ("causal", "following"):
        if all(f"{version}/{a}" in results for a in ("c0", "fitted_c")):
            continue
        scan.sky = {k: v.copy() for k, v in original.items()}
        if version == "following":
            scan.sky["position_km"][indexes] = p
            scan.sky["velocity_km_s"][indexes] = v

        def factory(*args):
            problem = geometry_problem(*args, mean_sigma=10, height_sigma=0)
            problem.problem.alias = list(locked)
            return problem

        fits = fit_once(scan, seed, "shared_phase", (0, 0), problem_class=factory)
        for a, f in fits.items():
            results[f"{version}/{a}"] = f
        write(path, results)
        print(case, version, {a: f["east_north_km"].tolist() for a, f in fits.items()}, flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    run(p.parse_args().case)
