"""Common-phase screening and all-bank competition for nominated curved families."""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases
from leo.analysis.research.track_evidence_objective import feasible_track_candidates

REPORT = ROOT / "reports/2026_10_17_cohort_phase_repair"


def scan(case, norad, fitted_c, output, *, all_candidates=False):
    arm = "fitted_c" if fitted_c else "c0"
    inventory = REPORT / "inventory" / case
    nomination = next(
        r for r in json.loads((inventory / "nominations.json").read_text()) if r["norad"] == norad
    )
    study, fit, source, _, _ = load_study(case, fitted_c)
    source_rows = json.loads((inventory / arm / "baseline_association.json").read_text())["rows"]
    bykey = {t["key"]: t for t in study.tracks}
    tracks = [bykey[k] for k in nomination["members"]]
    if not all(t["key"] in study.curved_keys for t in tracks):
        raise ValueError("linear fragment entered phase calibration")
    ids = sorted(oid for t in tracks for oid in t["observation_ids"])
    groups = [(t["key"], [t]) for t in tracks]
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    locked_norads = set()
    occupied = set()
    for other in ("c0", "fitted_c"):
        rows = json.loads((inventory / other / "baseline_association.json").read_text())["rows"]
        locked_norads.update(r["candidate_norad"] for r in rows if r["compatible"])
        occupied.update(r["component"] for r in rows if r["compatible"])
    if norad in locked_norads or any(t["key"] in occupied for t in tracks):
        raise ValueError("new family would recalibrate an established assignment")
    selected = (
        np.arange(len(study.sky["norad"]))
        if all_candidates
        else np.flatnonzero(study.sky["norad"] == norad)
    )
    sky = dict(
        time_s=study.sky["time_s"],
        position_km=study.sky["position_km"][selected],
        velocity_km_s=study.sky["velocity_km_s"][selected],
    )
    candidate_norads = study.sky["norad"][selected]
    locked = np.array([int(n) in locked_norads for n in candidate_norads])
    fixed_phase = np.asarray(fit["phases_s"])[selected]
    sigma, beta = study.sigma[selected], np.asarray(fit["beta"])
    grid = np.linspace(-15, 15, 601)
    scores = np.empty((len(grid), len(selected)))
    feasible = np.zeros_like(scores, bool)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            kernel_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/fixed_assignment_fit.py").read_bytes()
            ).hexdigest(),
            original_fit_path=str(source.relative_to(ROOT)),
            original_fit_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            inventory_sha256=hashlib.sha256(
                (inventory / "nominations.json").read_bytes()
            ).hexdigest(),
            bank_sha256=study.receipt["bank_sha256"],
            observation_ids=ids,
            members=nomination["members"],
            points=len(ids),
            only_curved_calibration=True,
            hardware_frozen=True,
            phases_of_previously_admitted_candidates_frozen=True,
            locked_norads=sorted(locked_norads),
            grid_points=601,
            phase_grid_s=[-15, 15],
            original_gaussian_priors_unchanged=True,
            all_members_must_pass=True,
            all_candidates=all_candidates,
            candidates=len(selected),
            candidate_ranking_after_all_member_gates=True,
            same_c0_calibration_population_for_both_c_arms=True,
            known_position_fixed=True,
            no_localization_accuracy_claim=True,
        ),
    )
    for index, value in enumerate(grid):
        phase = np.where(locked, fixed_phase, value)
        geometry = prepare_phase_geometry(sky, times, phase)
        f, e, h = phase_linear_frequency(geometry, fit["latitude_deg"], fit["longitude_deg"])
        stats = matching.statistics(
            groups,
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for t in tracks},
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phase)
        cost, terms = common_candidate_phase_scores(stats, beta, phase, sigma)

        def residual(fi, candidates, stats=stats, terms=terms, f=f):
            t, g = stats["fragments"][fi], stats["g"][fi]
            ix = np.searchsorted(times, t["times"])
            hardware = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                hardware += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            r = t["values"][None, :] - hardware - t["rf_hz"] / 11.5e9 * f[candidates][:, ix]
            r += terms.aliases[fi, candidates, None] * matching.PERIOD
            r -= terms.bias_hz[fi, candidates, None]
            return r

        scores[index] = cost
        feasible[index] = feasible_track_candidates(stats, terms, residual).all(axis=0)
        if all_candidates and (index + 1) % 100 == 0:
            status = dict(
                case=case,
                family=norad,
                arm=arm,
                phases=index + 1,
                candidates_passing=int(feasible[: index + 1].any(axis=0).sum()),
            )
            write(output / "progress.json", status)
            print(json.dumps(status), flush=True)
    rows = []
    for j in np.flatnonzero(feasible.any(axis=0)):
        i = int(np.argmin(np.where(feasible[:, j], scores[:, j], np.inf)))
        passing_phase = np.where(locked[j], fixed_phase[j], grid[feasible[:, j]])
        rows.append(
            dict(
                norad=int(candidate_norads[j]),
                score=float(scores[i, j]),
                phase_s=float(fixed_phase[j] if locked[j] else grid[i]),
                passing_phase_min_s=float(np.min(passing_phase)),
                passing_phase_max_s=float(np.max(passing_phase)),
                phase_locked=bool(locked[j]),
            )
        )
    rows.sort(key=lambda r: r["score"])
    np.savez_compressed(
        output / "phase_grid.npz",
        scores=scores,
        all_members_pass=feasible,
        phase_grid_s=grid,
        norad=candidate_norads,
        phase_locked=locked,
        locked_phase_s=fixed_phase,
    )
    summary = dict(
        case=case,
        nomination_norad=norad,
        fitted_c=fitted_c,
        members=nomination["members"],
        curved_points=len(ids),
        candidates=len(selected),
        passing_candidates=rows,
        uniquely_passing_nomination=(len(rows) == 1 and rows[0]["norad"] == norad),
        original_rows_sha256=hashlib.sha256(
            json.dumps(source_rows, sort_keys=True).encode()
        ).hexdigest(),
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


def run_screen():
    inventory = json.loads((REPORT / "inventory/summary.json").read_text())
    for case in inventory:
        for family in case["candidates"]:
            for fitted_c in (False, True):
                arm = "fitted_c" if fitted_c else "c0"
                scan(
                    case["case"],
                    family["norad"],
                    fitted_c,
                    REPORT / "screen" / case["case"] / str(family["norad"]) / arm,
                )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--screen-all", action="store_true")
    p.add_argument("--case", choices=[f"DSX01-S{i:02d}" for i in range(1, 6)])
    p.add_argument("--norad", type=int)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.screen_all:
        run_screen()
    else:
        if a.output is None or a.case is None or a.norad is None:
            p.error("case, norad and output required")
        if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
            p.error("QNAP is read-only")
        scan(a.case, a.norad, a.fitted_c, a.output, all_candidates=True)
