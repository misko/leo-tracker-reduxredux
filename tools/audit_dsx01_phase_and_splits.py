"""Exact bounded phase-grid and fixed midpoint split diagnostics on DSX01.

Independent fragment phases and fragment splitting are upper-bound diagnostic
freedoms, not physical satellite identifications or a promoted matching model.
"""

import argparse
import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from audit_dsx01_polynomial_satellite_gaps import evaluate_all

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.polynomial_satellite_diagnostics import (
    batch_noise_screen,
    orbit_shape_lower_bounds,
)

ROOT = Path(__file__).resolve().parents[1]
DELTAS = (0.0, -0.25, 0.25, -0.5, 0.5, -1.0, 1.0, -2.0, 2.0)


def statistics(tracks, times, frequency, elevation):
    return matching.statistics(
        [(t["key"], [t]) for t in tracks],
        dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
        {str(t["channel"]): 0.0 for t in tracks},
    )


def run(case, variant, cohort, output):
    output.mkdir(parents=True, exist_ok=False)
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter" / case
    fit_path = cohort / case / variant / "diagnosis.json"
    study = json.loads(fit_path.read_text())[0]
    fit, old = study["fit"], {r["component"]: r for r in study["association"]["rows"]}
    tracks = load_tracks(recording)
    sky = dict(np.load(Path(f"/tmp/ds22-shared-phase-bank-{case}/bank.npz")))
    t_all = np.unique(np.concatenate([t["times"] for t in tracks]))
    beta, phases = np.array(fit["beta"]), np.array(fit["phases_s"])
    support = np.zeros(4, bool)
    sat_support = set()
    for track in tracks:
        r = old[track["key"]]
        if r["compatible"] and r["active_curvature"]:
            support[matching.group(track)] = True
            sat_support.add(r["candidate_norad"])
    base_phase_allowed = (np.abs(phases) <= 1e-3) | np.isin(sky["norad"], list(sat_support))
    relaxed = [
        dict(
            component=t["key"],
            compatible=False,
            candidate_norad=None,
            phase_change_s=None,
            preferred_phase_s=None,
            rms_hz=None,
            current_candidate_can_pass=False,
            current_candidate_best_rms_hz=None,
        )
        for t in tracks
    ]
    details = []
    baseline = None
    for delta in DELTAS:
        phase = phases + delta
        allowed = np.abs(phase) <= sky["phase_bound_s"] + 1e-9
        if delta == 0:
            allowed &= base_phase_allowed
        frequency, elevation = phase_frequency_grid(
            sky, t_all, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phase
        )
        stats = statistics(tracks, t_all, frequency, elevation)
        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000.0)
        proposals = evaluate_all(tracks, stats, terms, beta, t_all, frequency, support, allowed)
        if delta == 0:
            baseline = frequency, elevation, stats, terms
            for fi, track in enumerate(tracks):
                ix = np.searchsorted(t_all, track["times"])
                g, q = matching.group(track), track["rf_hz"] / 11.5e9
                cal = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
                if len(beta) == 9:
                    cal += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
                observed = track["values"] - cal
                shape = orbit_shape_lower_bounds(observed, track["times"], q * frequency[:, ix])
                visible = stats["component_visible"][fi]
                jc = int(np.argmin(np.where(visible, shape["rms_offset_hz"], np.inf)))
                residual = observed - q * frequency[jc, ix] - shape["mean_hz"][jc]
                screen = batch_noise_screen(residual[None, :], track["times"])
                bias = (
                    shape["mean_hz"] + matching.PERIOD / 2
                ) % matching.PERIOD - matching.PERIOD / 2
                good = visible & (shape["rms_affine_hz"] <= 150) & (np.abs(bias) <= 3000)
                metrics = old[track["key"]]["residual_diagnostics"]
                failed = [
                    name
                    for name, key, limit in (
                        ("mean", "mean_z", 3),
                        ("slope", "slope_z", 3),
                        ("curvature", "quadratic_bic_gain", 10),
                        ("step", "maximum_step_z", 4),
                    )
                    if metrics[key] > limit
                ]
                if abs(metrics["lag1_acf"]) > 4 / np.sqrt(len(track["times"])):
                    failed.append("correlation")
                if old[track["key"]]["rms_hz"] > 450:
                    failed.append("rms")
                if abs(old[track["key"]]["bias_hz"]) > 3000:
                    failed.append("bias_bound")
                if not support[g]:
                    failed.append("hardware_support")
                details.append(
                    dict(
                        component=track["key"],
                        points=len(track["times"]),
                        active_curvature=old[track["key"]]["active_curvature"],
                        baseline_compatible=old[track["key"]]["compatible"],
                        baseline_failed_gates=failed,
                        best_offset_extra_slope_hz_s=float(shape["slope_hz_s"][jc]),
                        best_offset_noise_pass=bool(screen["noise_screen_pass"][0]),
                        best_offset_noise_metrics={
                            k: float(v[0]) for k, v in screen.items() if k != "noise_screen_pass"
                        },
                        minimum_extra_slope_for_affine_fit_with_bias_bound=None
                        if not good.any()
                        else float(np.min(np.abs(shape["slope_hz_s"][good]))),
                    )
                )
        for fi, (track, row) in enumerate(zip(tracks, proposals, strict=True)):
            if delta != 0 and not old[track["key"]]["active_curvature"]:
                continue
            current_index = int(
                np.flatnonzero(sky["norad"] == old[track["key"]]["candidate_norad"])[0]
            )
            own = relaxed[fi]
            value = float(np.sqrt(terms.residual_mse[fi, current_index]))
            if (
                own["current_candidate_best_rms_hz"] is None
                or value < own["current_candidate_best_rms_hz"]
            ):
                own["current_candidate_best_rms_hz"] = value
            own["current_candidate_can_pass"] |= current_index in row["feasible_candidates"]
            if row["compatible"] and (not own["compatible"] or row["rms_hz"] < own["rms_hz"]):
                j = row["candidate_index"]
                own.update(
                    compatible=True,
                    candidate_norad=int(sky["norad"][j]),
                    phase_change_s=delta,
                    preferred_phase_s=float(phase[j]),
                    rms_hz=row["rms_hz"],
                )
        write(output / "phase_grid.json", relaxed)
    frequency, elevation, stats, terms = baseline
    split = []
    for track in tracks:
        original = old[track["key"]]
        if original["compatible"] or len(track["times"]) < 24:
            continue
        mid = len(track["times"]) // 2
        halves, results = [], []
        for take in (slice(None, mid), slice(mid, None)):
            own = dict(
                track,
                times=track["times"][take],
                values=track["values"][take],
                observation_ids=track["observation_ids"][take],
            )
            if np.ptp(own["times"]) < 6:
                break
            ix = np.searchsorted(t_all, own["times"])
            local = statistics([own], own["times"], frequency[:, ix], elevation[:, ix])
            values = profile_component_bias(local, beta, bias_sigma_hz=1000.0)
            proposal = evaluate_all(
                [own],
                local,
                values,
                beta,
                own["times"],
                frequency[:, ix],
                support,
                base_phase_allowed,
            )[0]
            results.append(proposal)
            halves.append(
                dict(
                    points=len(own["times"]),
                    span_s=float(np.ptp(own["times"])),
                    compatible=proposal["compatible"],
                    candidate_norad=None
                    if not proposal["compatible"]
                    else int(sky["norad"][proposal["candidate_index"]]),
                    candidate_count=len(proposal["feasible_candidates"]),
                )
            )
        if len(halves) == 2:
            common = set(results[0]["feasible_candidates"]) & set(results[1]["feasible_candidates"])
            split.append(
                dict(
                    component=track["key"],
                    points=len(track["times"]),
                    halves=halves,
                    both_halves_compatible=all(r["compatible"] for r in halves),
                    common_candidates=len(common),
                )
            )
    write(output / "rejection_detail.json", details)
    write(output / "split_checks.json", split)
    summary = dict(
        case=case,
        variant=variant,
        baseline_points=study["association"]["compatible_points"],
        independent_phase_grid_points=sum(
            len(t["times"]) for t, r in zip(tracks, relaxed, strict=True) if r["compatible"]
        ),
        fixed_midpoint_both_halves_points=sum(
            r["points"] for r in split if r["both_halves_compatible"]
        ),
        fixed_midpoint_distinct_identity_needed_points=sum(
            r["points"] for r in split if r["both_halves_compatible"] and not r["common_candidates"]
        ),
        diagnostic_only_not_accepted_associations=True,
    )
    write(output / "summary.json", summary)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            input_fit_sha256=hashlib.sha256(fit_path.read_bytes()).hexdigest(),
            phase_change_grid_s=DELTAS,
            exact_orbit_geometry=True,
            causal_phase_bounds_preserved=True,
            hardware_frozen=True,
            nonlinear_fragments_only_for_nonzero_phase_changes=True,
            split_minimum_points=12,
            split_minimum_span_s=6,
            fixed_midpoint_only=True,
            independent_phases_are_diagnostic_upper_bound=True,
            no_position_estimate=True,
        ),
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True)
    p.add_argument("--cohort", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    for variant in ("c0", "fitted_c"):
        run(a.case, variant, a.cohort, a.output / a.case / variant)
