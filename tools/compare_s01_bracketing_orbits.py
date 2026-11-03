"""Matched past/future TLE sensitivity for nine S01 satellite-family hypotheses."""

import json

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from inventory_clipped_phase_cohort import load_study
from investigate_s01_ch4_t001 import OUTPUT, PRIOR, TARGET, residual_rows, statistics
from sgp4.api import Satrec

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.track_evidence_objective import profile_track_evidence
from leo.sky.propagation import ElementSetCatalogue

matplotlib.use("Agg")
import matplotlib.pyplot as plt

NORADS = [69333, 62811, 100168, 69523, 60372, 66163, 57784, 63474, 62052]


def run():
    source = json.loads((OUTPUT / "bracketing_tles.json").read_text())
    arms = {}
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, *_ = load_study("DSX01-S01", fc)
        fit = json.loads((PRIOR / arm / "fit_cap_2.7.json").read_text())
        association = json.loads((PRIOR / arm / "association_cap_2.7.json").read_text())
        arms[arm] = dict(study=study, fit=fit, beta=np.array(fit["beta"]), association=association)
    study = arms["c0"]["study"]
    banks = {}
    parity = {}
    for kind in ("past", "first_post_collection", "first_future_epoch"):
        chosen = [source[kind].get(str(n), source["past"][str(n)]) for n in study.sky["norad"]]
        cat = ElementSetCatalogue(tuple(r["name"] for r in chosen),
                                  tuple(int(n) for n in study.sky["norad"]),
                                  tuple(Satrec.twoline2rv(*r["lines"]) for r in chosen))
        p, v, usable = matching.ecef_states(cat, source["anchor_utc_ns"], study.sky["time_s"])
        assert usable.all()
        banks[kind] = dict(time_s=study.sky["time_s"], position_km=p, velocity_km_s=v,
                           norad=study.sky["norad"])
        parity[kind] = dict(
            maximum_position_difference_from_causal_km=float(np.max(np.abs(p - study.sky[
                "position_km"]))),
            maximum_velocity_difference_from_causal_km_s=float(np.max(np.abs(v - study.sky[
                "velocity_km_s"]))),
            available_candidates=sum(str(n) in source[kind] for n in study.sky["norad"]),
            fallback_to_past=[int(n) for n in study.sky["norad"] if str(n) not in source[kind]],
        )
        np.savez_compressed(OUTPUT / f"bank_{kind}.npz", **banks[kind])
    assert parity["past"]["maximum_position_difference_from_causal_km"] < 1e-8
    write(OUTPUT / "tle_bank_parity.json", parity)
    rows = arms["c0"]["association"]["association"]["rows"]
    summary = []
    details = {}
    for n in NORADS:
        keys = [r["component"] for r in rows if r["candidate_norad"] == n
                and r["active_curvature"]]
        tracks = [t for t in study.tracks if t["key"] in keys]
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        selected = np.flatnonzero(study.sky["norad"] == n)
        for kind in ("past", "first_future_epoch"):
            sky = {k: banks[kind][k][selected] for k in ("position_km", "velocity_km_s")}
            sky["time_s"] = study.sky["time_s"]
            states = {arm: [] for arm in arms}
            best_individual = {arm: {} for arm in arms}
            # Include each original fitted phase identically in both TLE arms.
            grid = np.unique(np.r_[np.linspace(-15, 15, 601),
                                   [a["fit"]["phases_s"][selected[0]] for a in arms.values()]])
            for value in grid:
                phase = np.array([value])
                geom = prepare_phase_geometry(sky, times, phase)
                fit = arms["c0"]["fit"]
                f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
                stats = statistics(tracks, times, f, e, h, phase)
                for arm, state in arms.items():
                    evidence, terms = profile_track_evidence(
                        stats, times, f, h, phase, state["beta"], phase, study.sigma[selected])
                    rr = residual_rows(tracks, times, f, terms, state["beta"],
                                       stats["component_visible"])
                    payload = dict(phase_s=float(value), score=evidence["score"],
                                   support_points=evidence["compatible_curved_points"], rows=rr)
                    states[arm].append(payload)
                    for r in rr:
                        previous = best_individual[arm].get(r["component"])
                        if previous is None or r["rms_hz"] < previous["rms_hz"]:
                            best_individual[arm][r["component"]] = dict(phase_s=float(value), **r)
            for arm, profile in states.items():
                best = min(profile, key=lambda r: r["score"])
                key = f"{arm}/{n}/{kind}"
                details[key] = dict(best_shared_phase=best, best_individual=best_individual[arm])
                longest = max(tracks, key=lambda t: np.ptp(t["times"]))["key"]
                indiv = best_individual[arm][longest]
                row = dict(arm=arm, norad=n, tle=kind, curved_fragments=len(tracks),
                           curved_points=sum(len(t["times"]) for t in tracks),
                           chosen_shared_phase_s=best["phase_s"],
                           shared_support_points=best["support_points"],
                           shared_support_fragments=sum(r["passing"] for r in best["rows"]),
                           longest_fragment=longest, longest_best_rms_hz=indiv["rms_hz"],
                           longest_best_phase_s=indiv["phase_s"],
                           longest_best_passing=indiv["passing"],
                           longest_any_phase_passing=any(next(r for r in s["rows"]
                                                             if r["component"] == longest)[
                                                                 "passing"] for s in profile))
                summary.append(row)
            print(json.dumps(dict(norad=n, tle=kind, rows=summary[-2:])), flush=True)
        write(OUTPUT / "tle_comparison_progress.json", summary)
        write(OUTPUT / "tle_comparison_details.json", details)
    write(OUTPUT / "tle_comparison_summary.json", summary)
    write(OUTPUT / "tle_comparison_protocol.json", dict(
        supplied_position_and_hardware_fixed=True, nine_family_labels_fixed_before_comparison=True,
        same_curved_points_aliases_phase_priors_and_grids_for_both_tle_arms=True,
        c0_and_fitted_c_matched=True, only_curved_nominees_calibrate_phase=True,
        linear_fragments_excluded=True, future_elements_not_causal_evidence=True,
        not_a_global_reassociation_or_localization_benchmark=True,
        best_individual_rms_is_diagnostic_not_a_shared_family_assignment=True,
    ))
    render(summary, details)


def render(summary, details):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for kind, label in (("past", "Causal TLE"), ("first_future_epoch", "First future-epoch TLE")):
        rs = [r for r in summary if r["arm"] == "fitted_c" and r["tle"] == kind]
        x = np.arange(len(rs)) + (-0.18 if kind == "past" else 0.18)
        axes[0].bar(x, [r["longest_best_rms_hz"] for r in rs], width=0.35, label=label)
        axes[1].bar(x, [r["shared_support_points"] for r in rs], width=0.35, label=label)
    for ax in axes:
        ax.set(xticks=np.arange(len(NORADS)), xticklabels=[str(n) for n in NORADS], xlabel="NORAD")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    axes[0].set(title="Longest fragment: best individual phase RMS", ylabel="Residual RMS (Hz)")
    axes[1].set(title="One shared phase per family: passing curved points",
                ylabel="Compatible curved GLRT points")
    fig.suptitle("DSX01 S01 — matched retrospective TLE sensitivity\n"
                 "Same GPS, hardware, labels, observations and phase priors; fitted-c")
    fig.savefig(OUTPUT / "future_tle_comparison.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained")
    for kind, label in (("past", "Causal TLE"), ("first_future_epoch", "Future-epoch TLE")):
        r = details[f"fitted_c/69333/{kind}"]["best_individual"][TARGET]
        axes[0].plot(r["times_s"], r["residual_hz"], "o-", ms=3,
                     label=f"{label}: {r['rms_hz']:.1f} Hz RMS, phase {r['phase_s']:.2f} s")
    axes[0].set(title="Longest unassociated track: best phase alone", ylabel="Residual (Hz)")
    for kind, label in (("past", "Causal"), ("first_future_epoch", "Future")):
        rows = details[f"fitted_c/69333/{kind}"]["best_shared_phase"]["rows"]
        target = next(r for r in rows if r["component"] == TARGET)
        axes[1].plot(target["times_s"], target["residual_hz"], ".-", label=f"{label} shared-phase")
    axes[1].set(title="Same track at the phase selected by the whole curved family",
                ylabel="Residual (Hz)")
    for ax in axes:
        ax.axhline(0, color="black", lw=0.7)
        ax.set(xlabel="Seconds from scan start")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(OUTPUT / "target_future_tle_residuals.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
