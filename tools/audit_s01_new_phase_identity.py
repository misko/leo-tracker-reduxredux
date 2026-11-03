"""All-bank identity competition for the newly phase-supported 62052 family."""

import json

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from deep_dive_longest_unassociated_s01 import CURRENT
from inventory_clipped_phase_cohort import load_study
from plot_s01_phase_sensitivity import OUTPUT

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases

MEMBERS = ["S01-RX1-CH3-T005", "S01-RX2-CH1-T001", "S01-RX2-CH6-T001"]


def selected_diagnostics():
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        fit = json.loads((OUTPUT / arm / "fit_cap_1.json").read_text())
        tracks = [t for t in study.tracks if t["key"] in MEMBERS]
        selected = np.flatnonzero(study.sky["norad"] == 62052)
        sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
        sky["time_s"] = study.sky["time_s"]
        phase = np.array([-1.0])
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        geom = prepare_phase_geometry(sky, times, phase)
        f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
        stats = matching.statistics(
            [(t["key"], [t]) for t in tracks],
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for t in tracks},
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phase)
        beta = np.array(fit["beta"])
        _, terms = common_candidate_phase_scores(stats, beta, phase, study.sigma[selected])
        rows = []
        for k, t in enumerate(tracks):
            g = matching.group(t)
            hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
            if len(beta) == 9:
                hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            residual = t["values"] - hw - t["rf_hz"] / 11.5e9 * f[0, np.searchsorted(
                times, t["times"])]
            residual += terms.aliases[k, 0] * matching.PERIOD - terms.bias_hz[k, 0]
            rows.append(dict(component=t["key"], points=len(residual),
                             rms_hz=float(np.sqrt(np.mean(residual**2))),
                             bias_hz=float(terms.bias_hz[k, 0]),
                             times_s=t["times"], residual_hz=residual,
                             diagnostics=matching.noise_screen(residual, t["times"])))
        pooled_t = np.concatenate([r["times_s"] for r in rows])
        pooled_r = np.concatenate([r["residual_hz"] for r in rows])
        order = np.argsort(pooled_t, kind="stable")
        pooled = matching.noise_screen(pooled_r[order], pooled_t[order])
        write(OUTPUT / arm / "62052_selected_residual_diagnostics.json",
              dict(phase_s=-1, members=rows, pooled=pooled,
                   all_individual_members_pass=all(r["diagnostics"]["noise_screen_pass"]
                                                   for r in rows),
                   pooled_independent_white_noise_screen_pass=pooled["noise_screen_pass"],
                   no_forced_single_merged_track=True))


def run():
    arms = {}
    grid = np.linspace(-15, 15, 601)
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        fit = json.loads((CURRENT / arm / "fit.json").read_text())
        arms[arm] = dict(study=study, fit=fit, beta=np.array(fit["beta"]),
                         passing=np.zeros((601, len(study.sky["norad"])), bool),
                         scores=np.full((601, len(study.sky["norad"])), np.inf))
    study = arms["c0"]["study"]
    tracks = [next(t for t in study.tracks if t["key"] == key) for key in MEMBERS]
    assert all(k in study.curved_keys for k in MEMBERS)
    times = np.unique(np.concatenate([t["times"] for t in tracks]))
    for i, value in enumerate(grid):
        phase = np.full(len(study.sky["norad"]), value)
        geom = prepare_phase_geometry(study.sky, times, phase)
        fit = arms["c0"]["fit"]
        f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
        stats = matching.statistics(
            [(t["key"], [t]) for t in tracks],
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for t in tracks},
        )
        stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phase)
        for state in arms.values():
            beta = state["beta"]
            scores, terms = common_candidate_phase_scores(stats, beta, phase, study.sigma)
            passing = np.ones(len(phase), bool)
            for k, t in enumerate(tracks):
                g = matching.group(t)
                ix = np.searchsorted(times, t["times"])
                hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
                if len(beta) == 9:
                    hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
                residual = t["values"] - hw - t["rf_hz"] / 11.5e9 * f[:, ix]
                residual += terms.aliases[k, :, None] * matching.PERIOD
                residual -= terms.bias_hz[k, :, None]
                passing &= (
                    stats["component_visible"][k]
                    & (np.mean(residual**2, axis=1) <= 450**2)
                    & (abs(terms.bias_hz[k]) <= 3000)
                    & batch_noise_screen(residual, t["times"])["noise_screen_pass"]
                )
            state["passing"][i] = passing
            state["scores"][i] = scores
        if (i + 1) % 100 == 0:
            print(json.dumps(dict(completed_phases=i + 1)), flush=True)
    for arm, state in arms.items():
        path = OUTPUT / arm
        np.savez_compressed(path / "62052_identity_grid.npz", phase_s=grid,
                            norad=study.sky["norad"], passing=state["passing"],
                            scores=state["scores"])
        candidates = []
        for j in np.flatnonzero(state["passing"].any(axis=0)):
            indexes = np.flatnonzero(state["passing"][:, j])
            best = indexes[np.argmin(state["scores"][indexes, j])]
            candidates.append(dict(norad=int(study.sky["norad"][j]),
                                   best_phase_s=float(grid[best]),
                                   score=float(state["scores"][best, j]),
                                   passing_phases_s=grid[indexes]))
        write(path / "62052_identity_audit.json", dict(
            members=MEMBERS, points=sum(len(t["times"]) for t in tracks),
            candidates=len(study.sky["norad"]), grid_points=601, range_s=[-15, 15],
            competitors_allowed_free_phase=True, all_three_members_must_pass=True,
            hardware_and_gps_fixed=True, passing_candidates=candidates,
            uniqueness_conditional_on_current_bank_and_phase_grid=True,
        ))
        print(json.dumps(dict(arm=arm, passing_candidates=[r["norad"] for r in candidates])),
              flush=True)


if __name__ == "__main__":
    run()
    selected_diagnostics()
