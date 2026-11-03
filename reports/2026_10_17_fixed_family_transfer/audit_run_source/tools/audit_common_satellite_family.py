"""All-candidate common-phase competition for the three clipped curved arcs."""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from search_track_evidence_position import PRIOR, ROOT, prepare
from transfer_fixed_satellite_families import FixedFamilies

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases
from leo.analysis.research.track_evidence_objective import feasible_track_candidates


def run(fitted_c, output):
    arm, case = "fitted_c" if fitted_c else "c0", "DSX01-S01"
    full, _, _, _, _, _ = prepare(case, fitted_c)
    source = FixedFamilies(case, False, False)
    groups = [
        (key, ms)
        for ci, (key, ms) in enumerate(source.groups)
        if source.norads[source.labels[ci]] == 100320
    ]
    times = np.unique(np.concatenate([t["times"] for _, ms in groups for t in ms]))
    target_ids = sorted(oid for _, ms in groups for t in ms for oid in t["observation_ids"])
    if len(target_ids) != 141 or len(set(target_ids)) != 141:
        raise ValueError("family population changed")
    known_path = PRIOR / "fits" / case / f"repaired_{arm}" / "fixed_site.json"
    frozen = json.loads(known_path.read_text())["fit"]
    beta = np.asarray(frozen["beta"])
    supported = set()
    for other in ("c0", "fitted_c"):
        before = (
            ROOT
            / "reports/2026_10_17_fixed_family_transfer/clipped_family_phase"
            / other
            / "before_association.json"
        )
        supported.update(
            r["candidate_norad"]
            for r in json.loads(before.read_text())["association"]["rows"]
            if r["compatible"] and r["active_curvature"]
        )
    locked = np.array([int(n) in supported for n in full.sky["norad"]])
    fixed_phases = np.asarray(frozen["phases_s"])
    grid = np.linspace(-15, 15, 601)
    scores = np.empty((len(grid), len(locked)))
    passed = np.zeros_like(scores, bool)
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            component_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/fixed_assignment_fit.py").read_bytes()
            ).hexdigest(),
            known_position_fit_sha256=hashlib.sha256(known_path.read_bytes()).hexdigest(),
            bank_sha256=full.receipt["bank_sha256"],
            observed_ids=target_ids,
            all_141_points_scored=True,
            measured_curved_fragments_only=True,
            one_shared_candidate_and_phase_for_all_three_arcs=True,
            candidates=len(locked),
            phase_grid_points=601,
            grid_seconds=[-15, 15],
            hardware_and_existing_supported_satellite_phases_frozen=True,
            phase_lock_set_union_of_c_arms=sorted(supported),
            gaussian_phase_priors_unchanged=True,
            c0_fitted_c_population_candidates_phase_lock_set_and_budgets_matched=True,
            candidate_ranking_after_every_member_noise_and_bias_gate=True,
            known_position_diagnostic=True,
            no_independent_identity_truth=True,
            grid_based_competition_not_global_continuous_phase_optimum=True,
        ),
    )
    for index, trial in enumerate(grid):
        phase = np.where(locked, fixed_phases, trial)
        geometry = prepare_phase_geometry(full.sky, times, phase)
        f, e, h = phase_linear_frequency(geometry, frozen["latitude_deg"], frozen["longitude_deg"])
        stats = matching.statistics(
            groups,
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for _, ms in groups for t in ms},
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phase)
        value, terms = common_candidate_phase_scores(stats, beta, phase, full.sigma)

        def residual(fi, candidates):
            track, g = stats["fragments"][fi], stats["g"][fi]
            ix = np.searchsorted(times, track["times"])
            hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
            if len(beta) == 9:
                hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            r = track["values"][None, :] - hardware - track["rf_hz"] / 11.5e9 * f[candidates][:, ix]
            r += terms.aliases[fi, candidates, None] * matching.PERIOD
            r -= terms.bias_hz[fi, candidates, None]
            return r

        scores[index] = value
        passed[index] = feasible_track_candidates(stats, terms, residual).all(axis=0)
        if (index + 1) % 50 == 0:
            progress = dict(
                phases_evaluated=index + 1,
                candidates_ever_passing=int(np.any(passed[: index + 1], axis=0).sum()),
            )
            write(output / "progress.json", progress)
            print(json.dumps(progress), flush=True)
    rows = []
    for j in np.flatnonzero(passed.any(axis=0)):
        i = int(np.argmin(np.where(passed[:, j], scores[:, j], np.inf)))
        rows.append(
            dict(
                norad=int(full.sky["norad"][j]),
                score=float(scores[i, j]),
                phase_s=float(fixed_phases[j] if locked[j] else grid[i]),
                phase_was_previously_supported=bool(locked[j]),
                passing_grid_samples=int(passed[:, j].sum()),
            )
        )
    rows.sort(key=lambda r: r["score"])
    np.savez_compressed(
        output / "candidate_phase_grid.npz",
        scores=scores,
        all_members_pass=passed,
        phase_grid_s=grid,
        norad=full.sky["norad"],
        locked=locked,
        locked_phase_s=fixed_phases,
    )
    write(output / "passing_candidates.json", rows)
    summary = dict(
        candidates=len(locked),
        phases=601,
        passing_candidates=len(rows),
        ranked_passing_candidates=rows,
        fitted_c=fitted_c,
        independent_identity_truth=False,
        grid_based_audit=True,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.fitted_c, a.output)
