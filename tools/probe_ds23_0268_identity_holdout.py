"""Catalogue identity sensitivity with the disputed family absent from RF fit.

This is a conditional diagnostic, not a replacement association policy. Both
receiver calibration and position are relearned without any 53923 measurements.
No evaluation coordinates or post-scan elements are read here.
"""

import copy
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from ablate_ds23_frequency_event_satellites import removal_mask
from algo02_scan import pair_passes
from debug_ds23_0268_visibility_reentry import OUT
from investigate_ds23_0268_remaining_tracks import load, fine_receiver_basis
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_frequency_events import refit, cached
from ds23_frequency_events import make_event_problem, attach_event_predictive
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen


FIT = OUT / "identity_family_excluded_fit.json"
RESULT = OUT / "identity_family_excluded_screen.json"


def calibrated_values(problem, state, track_index):
    """Use the event-aware scan view, including fitted receiver change events."""
    t = problem.scan.tracks[track_index]
    return (t["values"] - problem.scan.hardware(t, state["beta"]) -
            t["rf_hz"] / 11.5e9 * problem.scan.rx_basis[track_index] @
            state["smooth"][t["receiver"] - 1])


def setup():
    scan, base, saved, _, _ = load()
    selected = read(OUT / "trials/interior_add_66797.json")
    old = context("DS23-0268")[4]
    changed = copy.copy(scan)
    changed.rx_basis = [fine_receiver_basis(t["times"]) for t in scan.tracks]
    # selected nominations must be used, including the new 66797 family.
    keep, entries = removal_mask(selected["node"]["seed"]["rows"], base.slices,
        selected["mask"], old["linear_entries"], norads=(53923,))
    hyper = old["hyperparameters_from_pre_RF_TLE_only"]
    labels = sorted({r["candidate_index"] for r in selected["node"]["seed"]["rows"]})
    _, receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(receipts, hyper["shrinkage"])
    return changed, base, selected, keep, entries, hyper, means, saved


def fit_arm(arm):
    scan, _, selected, keep, entries, hyper, means, saved = setup()
    return refit(scan, selected["node"], keep, arm, np.asarray(selected["powers"]),
        means, hyper, saved["events"], entries)


def main():
    source = OUT / "trials/interior_add_66797.json"
    if not FIT.exists():
        with ProcessPoolExecutor(max_workers=2) as pool:
            arms = dict(zip(("c0", "fitted_c"), pool.map(fit_arm, ("c0", "fitted_c")), strict=True))
        scan, base, selected, keep, entries, _, _, _ = setup()
        write(FIT, dict(arms=arms, paired_valid=pair_passes(arms, include_linear=True),
            mask=keep, entries=entries, all_53923_measurements_excluded_from_fit=True,
            source_sha256=sha(source), cold_start_km=[0, 0], phase_rounds=5,
            position_steps_per_round=48, GPS_used=False, future_TLE_used=False))
    fit = read(FIT)
    if fit["source_sha256"] != sha(source):
        raise ValueError("identity control starting model changed")
    if RESULT.exists():
        raise FileExistsError("preserve completed identity screen")
    scan, base, selected, keep, entries, hyper, means, saved = setup()
    disputed = [i for row, i in zip(base.rows, base.members, strict=True)
                if row["candidate_norad"] == 53923]
    if len(disputed) != len(set(disputed)):
        raise ValueError("duplicate disputed curves")
    groups = dict(all_six=list(range(len(disputed))),
        RX1=[m for m, i in enumerate(disputed) if scan.tracks[i]["receiver"] == 1],
        RX2=[m for m, i in enumerate(disputed) if scan.tracks[i]["receiver"] == 2])
    phases = np.linspace(-15, 15, 121)
    times = np.unique(np.concatenate([scan.tracks[i]["times"] for i in disputed]))
    scores = {arm: np.zeros((len(phases), len(scan.norads), len(disputed)))
              for arm in ("c0", "fitted_c")}
    passing = {arm: np.zeros_like(a, dtype=bool) for arm, a in scores.items()}
    prepared = {}
    for arm, result in fit["arms"].items():
        p = make_event_problem(scan, selected["node"], keep, arm,
            np.asarray(result["phase_reference"]), np.asarray(selected["powers"]), means, hyper, saved["events"])
        attach_event_predictive(p, entries, np.asarray(selected["powers"]))
        cached(p)
        x = np.asarray(result["endpoint_east_north_km"])
        if abs(p.calculate(x)["negative_twice_elbo"] - result["negative_twice_elbo"]) > 1e-3:
            raise ValueError("family-excluded RF fit no longer replays")
        s = p.state(x)
        observed = []
        for i in disputed:
            observed.append(calibrated_values(p, s, i))
        prepared[arm] = (x, observed)
    for k, phase in enumerate(phases):
        geometry = prepare_phase_geometry(scan.sky, times, np.full(len(scan.norads), phase))
        for arm, (x, observed) in prepared.items():
            frequency, elevation, _ = phase_linear_frequency(geometry, *latlon(x))
            for m, i in enumerate(disputed):
                t = scan.tracks[i]
                indices = np.searchsorted(times, t["times"])
                terms = profile(observed[m], t["rf_hz"] / 11.5e9 * frequency[:, indices], *scan.white[i])
                noise = batch_noise_screen(terms["innovations"], t["times"])
                visible = elevation[:, indices].min(axis=1) >= 0
                scores[arm][k, :, m] = np.where(visible, terms["cost"], np.inf)
                passing[arm][k, :, m] = (visible & (terms["rms"] <= 450) &
                    (abs(terms["bias"]) <= 3000) & noise["noise_screen_pass"])
        if (k + 1) % 30 == 0:
            print("family-excluded catalogue phase", k + 1, "/", len(phases), flush=True)
    result = {}
    for arm, array in scores.items():
        result[arm] = {}
        for group, which in groups.items():
            cost = array[:, :, which].sum(axis=2)
            best_phase = np.argmin(cost, axis=0)
            best = cost[best_phase, np.arange(len(scan.norads))]
            ranking = np.argsort(best)
            ranks = {int(scan.norads[j]): rank + 1 for rank, j in enumerate(ranking)}
            candidates = list(ranking[:8])
            candidates += [int(np.flatnonzero(scan.norads == n)[0]) for n in (53923, 67953)]
            result[arm][group] = [dict(norad=int(scan.norads[j]), rank=ranks[int(scan.norads[j])],
                phase_s=float(phases[best_phase[j]]), curve_score=float(best[j]),
                all_local_tracks_pass=bool(passing[arm][best_phase[j], j, which].all()))
                for j in dict.fromkeys(candidates)]
    write(RESULT, dict(arms=result, causal_catalogue_candidates=len(scan.norads),
        fit_sha256=sha(FIT), fit_paired_valid=fit["paired_valid"], phase_grid_s=phases,
        conditional_nomination_only=True, all_53923_measurements_excluded_from_calibration_and_position=True,
        one_shared_phase_per_group=True, no_candidate_orbit_modes_or_phase_prior_in_screen=True,
        calibration_uncertainty_not_integrated_in_proposal_scores=True,
        no_GPS_or_future_TLE_used=True, source_sha256=sha(ROOT / "tools/probe_ds23_0268_identity_holdout.py")))
    print({arm: {group: rows[:2] for group, rows in groups.items()}
           for arm, groups in result.items()}, flush=True)


if __name__ == "__main__":
    main()
