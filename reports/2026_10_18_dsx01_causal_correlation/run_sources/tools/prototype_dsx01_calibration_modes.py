"""Keep distinct blind radio/identity basins instead of one tight-prior seed."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from evaluate_shared_satellite_phase import improve
from iterate_dsx01_position_nominations import fit_once, nomination_rows
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_continuous_position import CENTER, native_point, numpy_state
from prototype_dsx01_receiver_geometry import SOURCE, geometry_problem

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, proposal_phases

OUTPUT = ROOT / "reports/2026_10_18_dsx01_calibration_modes"


def project_radio_state(state):
    """Project proposal drifts to the final RX mean/contrast box before scoring."""
    state = numpy_state(state)
    for receiver in range(2):
        rates = state["beta"][4 + 2 * receiver : 6 + 2 * receiver] / 150
        mean = np.clip(rates.mean(), -30, 30)
        contrast = np.clip((rates[1] - rates[0]) / 2, -1.5, 1.5)
        state["beta"][4 + 2 * receiver : 6 + 2 * receiver] = 150 * np.array(
            [mean - contrast, mean + contrast]
        )
    state["beta"][:4] = (state["beta"][:4] + PERIOD / 2) % PERIOD - PERIOD / 2
    return state


def distinct(a, b):
    rows_a = {r["component"]: r["candidate_norad"] for r in a["seed"]["rows"]}
    rows_b = {r["component"]: r["candidate_norad"] for r in b["seed"]["rows"]}
    if rows_a.keys() != rows_b.keys():
        raise ValueError("calibration hypotheses must preserve the curved population")
    labels = sum(rows_a[k] != rows_b[k] for k in rows_a)
    delta = np.array(a["seed"]["state"]["beta"][:4]) - b["seed"]["state"]["beta"][:4]
    delta = (delta + PERIOD / 2) % PERIOD - PERIOD / 2
    return labels >= 2 or np.sqrt(np.mean(delta**2)) >= 500


def select_modes(candidates, retain):
    selected = []
    for item in sorted(candidates, key=lambda r: (r["center_score"], r["hypothesis"])):
        if all(distinct(item, previous) for previous in selected):
            selected.append(item)
        if len(selected) == retain:
            break
    return selected


def choose_pair(choices):
    """Select a single hypothesis by c0; fitted c receives its matched partner."""
    key = min(choices, key=lambda k: choices[k]["c0"]["score"])
    return key, choices[key]


def center_profile(scan, seed, *, iterations=12):
    p = geometry_problem(scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0)
    initial = np.clip(p.initial, p.lower, p.upper)

    def residual(z):
        return p.residual(np.r_[0.0, 0.0, z])

    fit = bounded_gauss_newton(
        residual, initial[2:], p.lower[2:], p.upper[2:], iterations=iterations
    )
    x = np.r_[0.0, 0.0, fit["parameters"]]
    return dict(rows=p.rows, state=p.decode(x)), dict(
        score=fit["score"],
        evaluations=fit["evaluations"],
        stopped=fit["stopped"],
        aliases=p.alias,
        fixed_position_km=[0, 0],
    )


def discovery(case, *, budget=8, retain=4):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "seed_bundle.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["budget"] != budget or saved["retain"] != retain:
            raise ValueError("existing discovery uses another budget; preserve its artifacts")
        return saved
    progress_path = directory / "discovery_progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else []
    scan = Scan(case)
    base = phase_linear_frequency(scan.geometry, *CENTER)
    stats = matching.statistics(
        scan.groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    assert stats["active"].all() and stats["fragment_active"].all()
    initial = np.zeros(8)
    bounds = np.full(len(scan.norads), 15.0)
    phases, _ = proposal_phases(stats, initial, scan.sigma, bounds, return_components=True)
    phi = phases[stats["ci"]]
    seed_stats = dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phi,
        xz=stats["xz"] - stats["xh"] * phi,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phi + stats["hh"] * phi**2),
    )
    shape = np.maximum(
        0, seed_stats["rss"] - seed_stats["xz"] ** 2 / np.maximum(stats["xx"][:, None], 1e-12)
    )
    seed_stats["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, stats["starts"], axis=0) / stats["count"][:, None]
    )
    proposals = list(
        itertools.islice(matching.seed_calibrations(seed_stats, initial, budget), budget)
    )
    inherited = json.loads((SOURCE / case / "shared_phase_center.json").read_text())
    for number in range(len(progress), len(proposals) + 1):
        if number == len(proposals):
            state = project_radio_state(inherited["state"])
            heuristic = None
        else:
            beta = proposals[number]
            phase = (
                np.zeros(len(scan.norads))
                if number == 0
                else proposal_phases(stats, beta, scan.sigma, bounds)
            )
            result = improve(
                stats, beta, phase, scan.sigma, bounds, drift_sigma_hz_s=10, drift_bound_hz_s=30
            )
            heuristic = float(result[0])
            state = project_radio_state(
                dict(beta=result[1], phases=result[2], extra={}, smooth=np.zeros((2, 11)))
            )
        # No legacy update: it would silently reinstate +/-1 Hz/s band bounds.
        _, rows, nominees, _ = scan.association(
            state, base, native_point(scan, (0, 0)), "shared_phase"
        )
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        profiles = []
        for _ in range(2):
            seed, detail = center_profile(scan, seed)
            profiles.append(detail)
            seed, _ = explore(
                scan, numpy_state(seed["state"]), (0, 0), "shared_phase", compact_update=False
            )
        p = geometry_problem(
            scan, seed, "shared_phase", False, (0, 0), mean_sigma=10, height_sigma=0
        )
        x = np.clip(p.initial, p.lower, p.upper)
        z = p.residual(x)
        item = dict(
            hypothesis=number,
            origin="inherited_tight" if number == len(proposals) else "wide_proposal",
            proposal_independent_band_prior_score=heuristic,
            center_score=float(z @ z) + len(x) * np.log(len(p.flat_times)),
            seed=seed,
            profiles=profiles,
            center_parameters=len(x),
        )
        progress.append(item)
        write(progress_path, progress)
        print(case, "center", number, item["center_score"], flush=True)
    selected = select_modes(progress, retain)
    saved = dict(
        case=case,
        budget=budget,
        retain=retain,
        selected=[r["hypothesis"] for r in selected],
        candidates=progress,
    )
    write(path, saved)
    write(
        directory / "discovery_protocol.json",
        dict(
            no_GPS_or_oracle_or_future_TLE_input=True,
            only_original_individually_curved_observations=True,
            original_heuristic_proposal_seed_drift_bound_hz_s=matching.DRIFT_BOUND_HZ_S,
            proposal_independent_band_sigma_hz_s=10,
            proposal_independent_band_bound_hz_s=30,
            final_receiver_mean_contrast_sigmas_hz_s=[10, 0.5],
            final_mean_contrast_bounds_hz_s=[30, 1.5],
            center_profiles_per_proposal=2,
            nuisance_iterations_per_center_profile=12,
            center_nomination_refresh_uses_coherent_phase=True,
            legacy_tight_update_disabled=True,
            distinct_if_two_labels_differ_or_wrapped_offset_RMS_exceeds_hz=500,
            selection_by_center_objective_only=True,
            maximum_distinct_modes=retain,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    return saved


def run(case, method, *, rounds=1):
    bundle = discovery(case)
    scan = Scan(case)
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints_by_mode.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for item in bundle["candidates"]:
        if item["hypothesis"] not in bundle["selected"]:
            continue
        name = f"mode_{item['hypothesis']}"
        seed = item["seed"]
        anchor = (0, 0)
        for iteration in range(rounds + 1):
            key = f"{name}/round_{iteration}"
            if key in results:
                fits = results[key]
            else:
                if iteration:
                    seed, _ = explore(
                        scan, numpy_state(seed["state"]), anchor, method, compact_update=False
                    )
                # Method-specific split proposals are recomputed at the same
                # blind anchor. Extra/smooth state starts at zero for new labels.
                if not iteration and method != "shared_phase":
                    seed, _ = explore(
                        scan, numpy_state(seed["state"]), anchor, method, compact_update=False
                    )

                def factory(*args):
                    return geometry_problem(*args, mean_sigma=10, height_sigma=0)

                fits = fit_once(scan, seed, method, anchor, problem_class=factory)
                results[key] = fits
                write(path, results)
                print(
                    case, method, key, {a: f["east_north_km"] for a, f in fits.items()}, flush=True
                )
            seed = fits["c0"]
            anchor = seed["east_north_km"]
    chosen, pair = choose_pair(results)
    write(
        directory / "new_mode_selection.json",
        dict(selected=chosen, fits=pair, selector="c0_frequency_prior_plus_parameter_count_log_n"),
    )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS)
    p.add_argument("--discover-only", action="store_true")
    p.add_argument("--rounds", type=int, default=1)
    a = p.parse_args()
    discovery(a.case) if a.discover_only else run(
        a.case, a.method or "receiver_smooth", rounds=a.rounds
    )
