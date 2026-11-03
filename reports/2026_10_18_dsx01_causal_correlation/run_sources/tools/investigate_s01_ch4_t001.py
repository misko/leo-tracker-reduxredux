"""Diagnose S01's longest remaining unassociated graph polynomial."""

import argparse
import json

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.robust_polynomial_order import polynomial_orders
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases
from leo.analysis.research.track_evidence_objective import profile_track_evidence

OUTPUT = ROOT / "reports/2026_10_17_s01_ch4_t001_diagnosis"
PARENT_OUTPUT = OUTPUT
PRIOR = ROOT / "reports/2026_10_17_s01_phase_sensitivity"
TARGET = "S01-RX1-CH4-T001"


def statistics(tracks, times, f, e, h, phases):
    stats = matching.statistics(
        [(t["key"], [t]) for t in tracks],
        dict(time_s=times, doppler_0=f, elevation_deg=e),
        {str(t["channel"]): 0.0 for t in tracks},
    )
    return recenter_phases(augment_phase_statistics(stats, times, f, h), phases)


def residual_rows(tracks, times, f, terms, beta, visible):
    rows = []
    for k, t in enumerate(tracks):
        g = matching.group(t)
        hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
        if len(beta) == 9:
            hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
        residual = t["values"] - hw - t["rf_hz"] / 11.5e9 * f[0, np.searchsorted(
            times, t["times"])]
        residual += terms.aliases[k, 0] * matching.PERIOD - terms.bias_hz[k, 0]
        noise = matching.noise_screen(residual, t["times"])
        rms = float(np.sqrt(np.mean(residual**2)))
        x = t["times"] - np.mean(t["times"])
        slope = float(x @ residual / (x @ x))
        rows.append(dict(component=t["key"], points=len(residual), rms_hz=rms,
                         bias_hz=float(terms.bias_hz[k, 0]), slope_hz_s=slope,
                         passing=bool(visible[k, 0] and rms <= 450
                                      and abs(terms.bias_hz[k, 0]) <= 3000
                                      and noise["noise_screen_pass"]),
                         residual_hz=residual, times_s=t["times"], diagnostics=noise))
    return rows


def run(*, profiles_only=False, bank_kind="past"):
    OUTPUT.mkdir(exist_ok=True)
    arms = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        if bank_kind == "first_future_epoch":
            with np.load(PARENT_OUTPUT / "bank_first_future_epoch.npz") as bank:
                assert np.array_equal(bank["norad"], study.sky["norad"])
                study.sky = {**study.sky, **{k: bank[k] for k in bank.files}}
        fit = json.loads((PRIOR / arm / "fit_cap_2.7.json").read_text())
        association = json.loads((PRIOR / arm / "association_cap_2.7.json").read_text())
        arms[arm] = dict(study=study, fit=fit, association=association,
                         beta=np.array(fit["beta"]))
    study = arms["c0"]["study"]
    target = next(t for t in study.tracks if t["key"] == TARGET)
    write(OUTPUT / "track.json", target)
    write(OUTPUT / "polynomial_orders.json", polynomial_orders(target["times"], target["values"]))
    family_keys = [r["component"] for r in arms["c0"]["association"]["association"]["rows"]
                   if r["candidate_norad"] == 69333 and r["active_curvature"]]
    family = [t for t in study.tracks if t["key"] in family_keys]
    selected = np.flatnonzero(study.sky["norad"] == 69333)
    sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
    sky["time_s"] = study.sky["time_s"]
    times = np.unique(np.concatenate([t["times"] for t in family]))
    currents = {arm: float(state["fit"]["phases_s"][selected[0]]) for arm, state in arms.items()}
    grid = np.unique(np.r_[np.arange(-3, 1.0001, 0.005), list(currents.values())])
    profiles = {arm: [] for arm in arms}
    for value in grid:
        phase = np.array([value])
        geom = prepare_phase_geometry(sky, times, phase)
        fit = arms["c0"]["fit"]
        f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
        stats = statistics(family, times, f, e, h, phase)
        for arm, state in arms.items():
            evidence, terms = profile_track_evidence(
                stats, times, f, h, phase, state["beta"], phase, study.sigma[selected])
            rows = residual_rows(family, times, f, terms, state["beta"],
                                 stats["component_visible"])
            profiles[arm].append(dict(phase_s=float(value), score=evidence["score"],
                                      support_points=evidence["compatible_curved_points"],
                                      rows=rows))
    for arm, profile in profiles.items():
        current = currents[arm]
        folder = OUTPUT / arm
        folder.mkdir(exist_ok=True)
        write(folder / "family_phase_profile.json", profile)
        previous = {r["component"] for r in arms[arm]["association"]["association"]["rows"]
                    if r["compatible"] and r["candidate_norad"] == 69333
                    and r["active_curvature"]}
        target_passing = [r for r in profile
                          if next(x for x in r["rows"] if x["component"] == TARGET)["passing"]]
        keep_all = [r for r in target_passing if all(x["passing"] for x in r["rows"]
                                                    if x["component"] in previous)]
        target_best = min(profile, key=lambda r: next(x for x in r["rows"]
                                                       if x["component"] == TARGET)["rms_hz"])
        best = min(profile, key=lambda r: r["score"])
        old = min(profile, key=lambda r: abs(r["phase_s"] - current))
        summary = dict(current_phase_s=current, current=old, minimum_target_rms=target_best,
                       best_family_evidence=best, target_passing_phases_s=[r["phase_s"]
                                                                       for r in target_passing],
                       previous_curved_support=sorted(previous),
                       target_and_all_previous_passing_phases_s=[r["phase_s"] for r in keep_all])
        write(folder / "family_summary.json", summary)
        print(json.dumps(dict(arm=arm, current_phase=current,
                              best_family_phase=best["phase_s"],
                              best_target_phase=target_best["phase_s"],
                              target_passing=len(target_passing),
                              joint_preserve_previous=len(keep_all))), flush=True)
    if profiles_only:
        return
    # Independent all-bank target competition; even established competitors may
    # choose their own phase. These diagnostic proposals do not change calibration.
    times = target["times"]
    grid = np.linspace(-15, 15, 601)
    matrices = {arm: dict(passing=np.zeros((601, len(study.sky["norad"])), bool),
                          rms=np.zeros((601, len(study.sky["norad"]))),
                          bias=np.zeros((601, len(study.sky["norad"]))),
                          scores=np.zeros((601, len(study.sky["norad"])))) for arm in arms}
    for i, value in enumerate(grid):
        phase = np.full(len(study.sky["norad"]), value)
        geom = prepare_phase_geometry(study.sky, times, phase)
        fit = arms["c0"]["fit"]
        f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
        stats = statistics([target], times, f, e, h, phase)
        for arm, state in arms.items():
            score, terms = common_candidate_phase_scores(stats, state["beta"], phase, study.sigma)
            beta = state["beta"]
            g = matching.group(target)
            hw = beta[g] + beta[g + 4] * (times - 150) / 150
            if len(beta) == 9:
                hw += beta[8] * (target["rf_hz"] / 1e9 - 11.5)
            residual = target["values"] - hw - target["rf_hz"] / 11.5e9 * f
            residual += terms.aliases[0, :, None] * matching.PERIOD
            residual -= terms.bias_hz[0, :, None]
            rms = np.sqrt(np.mean(residual**2, axis=1))
            noise = batch_noise_screen(residual, times)
            passing = (stats["component_visible"][0] & (rms <= 450)
                       & (abs(terms.bias_hz[0]) <= 3000) & noise["noise_screen_pass"])
            matrices[arm]["passing"][i] = passing
            matrices[arm]["rms"][i] = rms
            matrices[arm]["bias"][i] = terms.bias_hz[0]
            matrices[arm]["scores"][i] = score
        if (i + 1) % 100 == 0:
            print(json.dumps(dict(bank_phases=i + 1)), flush=True)
    for arm, arrays in matrices.items():
        np.savez_compressed(OUTPUT / arm / "identity_grid.npz", phase_s=grid,
                            norad=study.sky["norad"], **arrays)
        candidates = []
        for j in np.flatnonzero(arrays["passing"].any(axis=0)):
            indexes = np.flatnonzero(arrays["passing"][:, j])
            k = indexes[np.argmin(arrays["scores"][indexes, j])]
            candidates.append(dict(norad=int(study.sky["norad"][j]), phase_s=float(grid[k]),
                                   rms_hz=float(arrays["rms"][k, j]),
                                   bias_hz=float(arrays["bias"][k, j]),
                                   passing_phases_s=grid[indexes]))
        write(OUTPUT / arm / "identity_candidates.json", candidates)
        print(json.dumps(dict(arm=arm, candidates=[r["norad"] for r in candidates])), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles-only", action="store_true")
    parser.add_argument("--bank-kind", choices=("past", "first_future_epoch"), default="past")
    args = parser.parse_args()
    if args.bank_kind != "past":
        OUTPUT = PARENT_OUTPUT / args.bank_kind
    run(profiles_only=args.profiles_only, bank_kind=args.bank_kind)
