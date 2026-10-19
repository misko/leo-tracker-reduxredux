"""Refit radio/identity hypotheses at every geographic grid node, then locate."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_calibration_modes import choose_pair, discovery, project_radio_state
from prototype_dsx01_continuous_position import CENTER, GRID, latlon
from prototype_dsx01_receiver_geometry import OUTPUT as BASELINE
from prototype_dsx01_receiver_geometry import geometry_problem as legacy_geometry_problem

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton

OUTPUT = ROOT / "reports/2026_10_18_dsx01_geographic_calibration"


def geometry_problem(*args, **kwargs):
    return restore_radio_initialization(legacy_geometry_problem(*args, **kwargs))


def fixed_profile(scan, seed, method, point, *, iterations=6):
    seed = dict(seed, state=project_radio_state(seed["state"]))
    p = geometry_problem(scan, seed, method, False, point, mean_sigma=10, height_sigma=0)
    initial = np.clip(p.initial, p.lower, p.upper)

    def residual(z):
        return p.residual(np.r_[point, z])

    fit = bounded_gauss_newton(
        residual, initial[2:], p.lower[2:], p.upper[2:], iterations=iterations
    )
    x = np.r_[point, fit["parameters"]]
    return dict(
        seed=dict(rows=p.rows, state=p.decode(x)),
        aliases=p.alias,
        east_north_km=point,
        nuisance_fit=fit,
        frequency_prior_score=fit["score"],
        complexity_penalty=len(x) * np.log(len(p.flat_times)),
        score=fit["score"] + len(x) * np.log(len(p.flat_times)),
    )


def fine_pair(scan, record, method, *, iterations=24):
    seed, point = record["seed"], record["east_north_km"]
    fits = {}
    for arm in ("c0", "fitted_c"):
        p = geometry_problem(
            scan, seed, method, arm == "fitted_c", point, mean_sigma=10, height_sigma=0
        )
        p.problem.alias = list(record["aliases"])
        mark = time.monotonic()
        fit = bounded_gauss_newton(p.residual, p.initial, p.lower, p.upper, iterations=iterations)
        fit["start_east_north_km"] = point
        x = fit["parameters"]
        penalty = len(x) * np.log(len(p.flat_times))
        fits[arm] = dict(
            latitude_deg=latlon(x[:2])[0],
            longitude_deg=latlon(x[:2])[1],
            east_north_km=x[:2],
            frequency_prior_score=fit["score"],
            complexity_penalty=penalty,
            score=fit["score"] + penalty,
            state=p.decode(x),
            rows=p.rows,
            aliases=p.alias,
            fits=[fit],
            starts=[point],
            anchor=point,
            seconds=time.monotonic() - mark,
        )
    return fits


def incumbents(case, method):
    data = json.loads((BASELINE / case / method / "endpoints.json").read_text())
    choices = dict(original={a: data[f"mean_10_height_0/{a}"] for a in ("c0", "fitted_c")})
    path = (
        ROOT
        / "reports/2026_10_18_dsx01_receiver_identity"
        / case
        / method
        / "mean_10_iterations.json"
    )
    if path.exists():
        for row in json.loads(path.read_text()):
            choices[f"identity_round_{row['iteration']}"] = row["fits"]
    return choices


def run(case, method, *, coarse_iterations=6, fine_starts=3):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "grid_nodes.json"
    records = json.loads(path.read_text()) if path.exists() else []
    bundle = discovery(case)
    warm = next(
        r["seed"]["state"] for r in bundle["candidates"] if r["hypothesis"] == bundle["selected"][0]
    )
    scan = Scan(case)
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_future_TLE_input=True,
            center=CENTER,
            grid=GRID,
            original_curved_population_preserved=True,
            same_warm_center_state_at_each_node=True,
            radio_warm_start_restored_from_supplied_state_after_inner_legacy_clipping=True,
            coarse_common_preprocessing_is_c0_only=True,
            coarse_nuisance_iterations_each_round=coarse_iterations,
            coarse_identity_rounds=2,
            fine_starts_selected_by_c0_frequency_prior_plus_parameter_count_log_n=fine_starts,
            fine_iterations_per_start_per_c_arm=24,
            receiver_mean_contrast_sigmas_hz_s=[10, 0.5],
            final_selection_uses_c0_only_and_keeps_its_matched_fitted_c_partner=True,
            prior_blind_incumbents_remain_candidates=True,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for point in GRID:
        if any(np.array_equal(point, r["east_north_km"]) for r in records):
            continue
        state = project_radio_state(warm)
        profiles = []
        for _ in range(2):
            seed, proposals = explore(scan, state, point, method, compact_update=False)
            record = fixed_profile(scan, seed, method, point, iterations=coarse_iterations)
            profiles.append(
                dict(
                    frequency_prior_score=record["frequency_prior_score"],
                    score=record["score"],
                    candidate_hypotheses=proposals["candidate_hypotheses"],
                )
            )
            state = record["seed"]["state"]
        record["profiles"] = profiles
        records.append(record)
        write(path, records)
        print(case, method, "grid", len(records), point, record["score"], flush=True)
    selected = sorted(records, key=lambda r: r["score"])[:fine_starts]
    result_path = directory / "fine_fits.json"
    fine = json.loads(result_path.read_text()) if result_path.exists() else {}
    choices = incumbents(case, method)
    for k, record in enumerate(selected):
        name = f"profiled_start_{k}"
        if name not in fine:
            fine[name] = fine_pair(scan, record, method)
            write(result_path, fine)
            print(
                case,
                method,
                name,
                {a: f["east_north_km"] for a, f in fine[name].items()},
                flush=True,
            )
        choices[name] = fine[name]
    chosen, pair = choose_pair(choices)
    write(
        directory / "endpoints.json",
        dict(
            selected=chosen,
            fits=pair,
            all_c0_scores={k: v["c0"]["score"] for k, v in choices.items()},
        ),
    )
    return pair


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, default="receiver_smooth")
    a = p.parse_args()
    run(a.case, a.method)
