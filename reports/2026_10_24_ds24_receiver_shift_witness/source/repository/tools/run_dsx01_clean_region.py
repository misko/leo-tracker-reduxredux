"""Fresh regional discovery: no saved positions, labels, aliases or radio state.

All eligible regional candidates are scored by the existing proposal machinery.
The resulting finite assignment atlas is a heuristic search, not exhaustive
joint satellite/position inference. GPS belongs only in a separate reporter.
"""

import argparse
import itertools
import json
import time

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from dsx01_satellite_prior_controls import SatellitePriorControls
from evaluate_shared_satellite_phase import improve
from iterate_dsx01_position_nominations import nomination_rows
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_calibration_modes import project_radio_state, select_modes
from prototype_dsx01_continuous_position import CENTER, GRID, native_point, numpy_state
from prototype_dsx01_glrt_weighting import variance_samples
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, proposal_phases

OUTPUT = ROOT / "reports/2026_10_18_dsx01_clean_region"


def load_scan(case):
    scan = Scan(case)
    apply_measurements(scan, json.loads(measurement_path(case).read_text())["points"], "glrt300")
    path = ROOT / "reports/2026_10_18_dsx01_causal_repairs/glrt_scores.json"
    _, squares = variance_samples(scan, json.loads(path.read_text())[case]["scores"])
    return scan, float(np.sqrt(np.mean(squares)))


def standard_problem(scan, seed, sigma, *, fitted_c=False, aliases=None):
    seed = dict(seed, state=reference_state(seed["state"]))
    return SatellitePriorControls(
        scan, seed, fitted_c, variant="normal", sigma=sigma, aliases=aliases
    )


def reference_state(state):
    """Clip numerical expansion epochs to the bank; retain the absolute prior."""
    state = numpy_state(state)
    state["phases"] = np.clip(state["phases"], -15, 15)
    return state


def score_at(problem, point):
    r = problem.residual(np.asarray(point))
    return float(r @ r)


def zero_state(scan):
    return dict(
        beta=np.zeros(8),
        phases=np.zeros(len(scan.norads)),
        extra={},
        smooth=np.zeros((2, scan.rx_basis[0].shape[1])),
    )


def fresh_discovery(scan, sigma, *, budget=8):
    base = phase_linear_frequency(scan.geometry, *CENTER)
    stats = matching.statistics(
        scan.groups,
        dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
        {str(t["channel"]): 0.0 for t in scan.tracks},
    )
    stats = augment_phase_statistics(stats, scan.times, base[0], base[2])
    bounds = np.full(len(scan.norads), 15.0)
    initial = np.zeros(8)
    phases, _ = proposal_phases(stats, initial, scan.sigma, bounds, return_components=True)
    phi = phases[stats["ci"]]
    proposals_stats = dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phi,
        xz=stats["xz"] - stats["xh"] * phi,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phi + stats["hh"] * phi**2),
    )
    shape = np.maximum(
        0,
        proposals_stats["rss"]
        - proposals_stats["xz"] ** 2 / np.maximum(stats["xx"][:, None], 1e-12),
    )
    proposals_stats["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, stats["starts"], axis=0) / stats["count"][:, None]
    )
    proposals = list(
        itertools.islice(matching.seed_calibrations(proposals_stats, initial, budget), budget)
    )
    candidates = []
    for number, beta in enumerate(proposals):
        state = zero_state(scan)
        if number:
            phase = proposal_phases(stats, beta, scan.sigma, bounds)
            fitted = improve(
                stats, beta, phase, scan.sigma, bounds, drift_sigma_hz_s=10, drift_bound_hz_s=30
            )
            state.update(beta=fitted[1], phases=fitted[2])
        state = project_radio_state(state)
        _, rows, nominees, _ = scan.association(
            state, base, native_point(scan, (0, 0)), "shared_phase"
        )
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        for _ in range(2):
            problem = standard_problem(scan, seed, sigma)
            state = problem.state(np.zeros(2))
            seed, _ = explore(
                scan, reference_state(state), (0, 0), "receiver_smooth", compact_update=False
            )
        problem = standard_problem(scan, seed, sigma)
        seed = dict(rows=problem.rows, state=problem.state(np.zeros(2)))
        candidates.append(
            dict(
                hypothesis=number,
                center_score=score_at(problem, [0, 0]),
                seed=seed,
                aliases=problem.alias,
            )
        )
        print(scan.case, "fresh", number, candidates[-1]["center_score"], flush=True)
    return candidates


def run(case, budget=8):
    directory = OUTPUT / case
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "atlas.json").exists():
        return
    scan, sigma = load_scan(case)
    write(directory / "input_audit.json", scan.inference_input_audit)
    write(
        directory / "protocol.json",
        dict(
            region_center=CENTER,
            box_width_km=25,
            search_grid=GRID,
            zero_initial_radio_and_phase=True,
            inherited_seed_files_read=False,
            satellite_whitelist=None,
            candidate_count=len(scan.norads),
            candidate_filter="original broad regional visibility only",
            fresh_radio_proposal_budget=budget,
            all_curved_points_preserved=True,
            GPS_or_following_TLE_in_inference=False,
            sigma_hz=sigma,
            assignment_search=(
                "all-candidate proposals; three fresh center modes; node-wise identity refresh"
            ),
            surface_radius_km=10,
            surface_center="regional box center, never evaluation GPS",
            limitation="finite heuristic assignment atlas, not exhaustive joint marginalization",
        ),
    )
    mark = time.monotonic()
    path = directory / "discovery.json"
    candidates = (
        json.loads(path.read_text())
        if path.exists()
        else fresh_discovery(scan, sigma, budget=budget)
    )
    write(path, candidates)
    modes = select_modes(candidates, 3)
    path = directory / "atlas_progress.json"
    atlas = json.loads(path.read_text()) if path.exists() else []
    for point in GRID:
        if any(np.array_equal(r["point"], point) for r in atlas):
            continue
        choices = []
        for item in modes:
            seed, detail = explore(
                scan,
                reference_state(item["seed"]["state"]),
                point,
                "receiver_smooth",
                compact_update=False,
            )
            p = standard_problem(scan, seed, sigma)
            state = p.state(np.array(point))
            seed, _ = explore(
                scan, reference_state(state), point, "receiver_smooth", compact_update=False
            )
            p = standard_problem(scan, seed, sigma)
            choices.append(
                dict(
                    point=point,
                    center_mode=item["hypothesis"],
                    score=score_at(p, point),
                    seed=dict(rows=p.rows, state=p.state(np.array(point))),
                    aliases=p.alias,
                    candidate_hypotheses=detail["candidate_hypotheses"],
                )
            )
        atlas.append(min(choices, key=lambda r: r["score"]))
        write(path, atlas)
        print(case, "atlas", len(atlas), atlas[-1]["score"], flush=True)
    write(
        directory / "atlas.json", dict(nodes=atlas, seconds=time.monotonic() - mark, sigma_hz=sigma)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S0{k}" for k in range(1, 6)])
    parser.add_argument("--budget", type=int, default=8)
    args = parser.parse_args()
    run(args.case, args.budget)
