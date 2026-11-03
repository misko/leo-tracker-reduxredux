"""Known-position, fixed-hardware phase audit of one clipped curved family."""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from search_track_evidence_position import PRIOR, prepare
from transfer_fixed_satellite_families import SOURCE, FixedFamilies

from leo.analysis.research.fixed_assignment_fit import fixed_assignment_score
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases


def run(fitted_c, output):
    case, norad, arm = "DSX01-S01", 100320, "fitted_c" if fitted_c else "c0"
    original, _, _, _, recording, background = prepare(case, fitted_c)
    source = FixedFamilies(case, False, False)
    groups = [
        (key, members)
        for ci, (key, members) in enumerate(source.groups)
        if source.norads[source.labels[ci]] == norad
    ]
    if len(groups) != 3 or sum(len(t["times"]) for _, ms in groups for t in ms) != 141:
        raise ValueError("reviewed family population changed")
    times = np.unique(np.concatenate([t["times"] for _, ms in groups for t in ms]))
    j = original.sky["norad"].tolist().index(norad)
    sky = dict(
        time_s=original.sky["time_s"],
        position_km=original.sky["position_km"][[j]],
        velocity_km_s=original.sky["velocity_km_s"][[j]],
    )
    known_path = PRIOR / "fits" / case / f"repaired_{arm}" / "fixed_site.json"
    frozen = json.loads(known_path.read_text())["fit"]
    beta = np.asarray(frozen["beta"])
    phases = np.linspace(-15, 15, 601)
    labels, sigma = np.zeros(len(groups), int), original.sigma[[j]]
    rows = []
    for phase in phases:
        geometry = prepare_phase_geometry(sky, times, np.array([phase]))
        f, e, h = phase_linear_frequency(geometry, frozen["latitude_deg"], frozen["longitude_deg"])
        stats = matching.statistics(
            groups,
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for _, ms in groups for t in ms},
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), np.array([phase]))
        evidence, terms = fixed_assignment_score(stats, beta, np.array([phase]), sigma, labels)
        diagnostics, valid = [], True
        for fi, track in enumerate(stats["fragments"]):
            ix, g = np.searchsorted(times, track["times"]), stats["g"][fi]
            hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
            if len(beta) == 9:
                hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            r = track["values"] + terms.aliases[fi, 0] * matching.PERIOD - hardware
            r -= track["rf_hz"] / 11.5e9 * f[0, ix] + terms.bias_hz[fi, 0]
            screen = matching.noise_screen(r, track["times"])
            rms = float(np.sqrt(np.mean(r**2)))
            passed = bool(
                screen["noise_screen_pass"]
                and rms <= 450
                and abs(terms.bias_hz[fi, 0]) <= 3000
                and stats["visible"][fi, 0]
            )
            valid &= passed
            diagnostics.append(
                dict(
                    key=track["key"],
                    points=len(r),
                    rms_hz=rms,
                    compatible=passed,
                    diagnostics=screen,
                )
            )
        rows.append(
            dict(
                phase_s=float(phase),
                score=evidence["score"],
                all_members_pass=valid,
                members=diagnostics,
            )
        )
    best = min(rows, key=lambda r: r["score"])
    output.mkdir(parents=True, exist_ok=False)
    write(output / "phase_grid.json", rows)
    write(output / "best.json", best)
    original_association = population_association(
        original, frozen, load_tracks(recording), background
    )
    altered = dict(frozen, phases_s=list(frozen["phases_s"]))
    altered["phases_s"][j] = best["phase_s"]
    after = population_association(original, altered, load_tracks(recording), background)
    before_map, after_map = [], []
    track_map = {t["key"]: t for t in original.tracks}
    for assoc, dest in ((original_association, before_map), (after, after_map)):
        for r in assoc["association"]["rows"]:
            if r["compatible"]:
                dest.extend(
                    (oid, r["candidate_norad"])
                    for oid in track_map[r["component"]]["observation_ids"]
                )
    before_map, after_map = dict(before_map), dict(after_map)
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        norad=norad,
        previous_phase_s=frozen["phases_s"][j],
        best_phase_s=best["phase_s"],
        original_phase_sigma_s=float(sigma[0]),
        original_phase_bound_s=float(original.bounds[j]),
        target_points=141,
        all_target_members_pass=best["all_members_pass"],
        before_points=original_association["compatible_points"],
        after_points=after["compatible_points"],
        gained_points=len(after_map.keys() - before_map.keys()),
        lost_points=len(before_map.keys() - after_map.keys()),
        relabelled_points=sum(
            before_map[k] != after_map[k] for k in before_map.keys() & after_map.keys()
        ),
        merged_tracks=after["merged_tracks"],
        hardware_frozen=True,
        other_phases_frozen=True,
        evaluation_position_fixed=True,
        position_accuracy_claim=False,
    )
    write(output / "before_association.json", original_association)
    write(output / "after_association.json", after)
    write(output / "fit.json", altered)
    write(output / "summary.json", summary)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            original_known_position_fit_sha256=hashlib.sha256(known_path.read_bytes()).hexdigest(),
            nomination_blind_source_sha256=hashlib.sha256(
                (SOURCE / case / "c0/fit.json").read_bytes()
            ).hexdigest(),
            same_three_curved_tracks_in_both_c_arms=True,
            all_141_raw_points_used=True,
            hardware_and_other_satellite_phases_frozen=True,
            only_one_phase_parameter_estimated=True,
            phase_grid_seconds=[-15, 15],
            grid_points=601,
            original_gaussian_prior_unchanged=True,
            no_linear_fragment_calibration=True,
            no_position_search_performed=True,
            known_position_compatibility_not_independent_identity_validation=True,
        ),
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.fitted_c, a.output)
