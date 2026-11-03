"""Controlled phase-range sensitivity at the supplied DSX01 S01 position.

Only previously unsupported, multiply nominated curved families learn phases.
All old labels, hardware, and established satellite phases remain fixed.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import matplotlib
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from deep_dive_longest_unassociated_s01 import CURRENT
from evaluate_robust_curve_reassociation import population_association
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases
from leo.analysis.research.track_evidence_objective import profile_track_evidence

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT = ROOT / "reports/2026_10_17_s01_phase_sensitivity"
CAPS = [0, 0.5, 1, 2, 2.5, 2.7, 3, 4, 5, 10, 15]
RAW = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"


def choose_state(profile, bound):
    """Clutter remains available; never learn a phase from a single curve."""
    eligible = [
        r for r in profile
        if abs(r["phase_s"]) <= bound + 1e-9 and len(r["supporting_members"]) >= 2
        and r["score"] < r["all_clutter_score"]
    ]
    return min(eligible, key=lambda r: r["score"]) if eligible else None


class Bound:
    def __init__(self, experiment, labels):
        self.experiment, self.labels = experiment, labels
        self.tracks, self.sky = experiment.tracks, experiment.sky

    def associate(self, fit):
        return self.experiment.associate(fit, fixed_labels=self.labels)


def run():
    OUTPUT.mkdir(exist_ok=True)
    raw = [r for line in RAW.read_text().splitlines()
           if (r := json.loads(line))["source_id"] == "S01"]
    raw_ids = {r["observation_id"] for r in raw}
    assert len(raw) == len(raw_ids) == 4797
    arms = {}
    locked, occupied = set(), set()
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, _, _, recording, background = load_study("DSX01-S01", fc)
        fit = json.loads((CURRENT / arm / "fit.json").read_text())
        old = json.loads((CURRENT / arm / "association.json").read_text())
        arms[arm] = study, fit, old, recording, background
        locked.update(r["candidate_norad"] for r in old["association"]["rows"]
                      if r["compatible"] and r["active_curvature"])
        occupied.update(r["component"] for r in old["association"]["rows"]
                        if r["compatible"] and r["active_curvature"])
    families = defaultdict(list)
    for row in arms["c0"][2]["association"]["rows"]:
        if (row["active_curvature"] and row["component"] not in occupied
                and row["candidate_norad"] not in locked):
            families[row["candidate_norad"]].append(row["component"])
    families = {n: keys for n, keys in families.items() if len(keys) >= 2}
    write(OUTPUT / "families.json", families)
    summaries, distributions = [], {}
    for arm, (study, fit, old, recording, background) in arms.items():
        folder = OUTPUT / arm
        folder.mkdir(exist_ok=True)
        mapping = {t["key"]: t for t in study.tracks}
        beta = np.array(fit["beta"])
        profiles = {}
        for norad, keys in families.items():
            tracks = [mapping[k] for k in keys]
            assert all(k in study.curved_keys for k in keys)
            selected = np.flatnonzero(study.sky["norad"] == norad)
            sky = {k: study.sky[k][selected] for k in ("position_km", "velocity_km_s")}
            sky["time_s"] = study.sky["time_s"]
            times = np.unique(np.concatenate([t["times"] for t in tracks]))
            saved = []
            for value in np.linspace(-15, 15, 601):
                phase = np.array([value])
                geom = prepare_phase_geometry(sky, times, phase)
                f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
                stats = matching.statistics(
                    [(t["key"], [t]) for t in tracks],
                    dict(time_s=times, doppler_0=f, elevation_deg=e),
                    {str(t["channel"]): 0.0 for t in tracks},
                )
                stats = recenter_phases(augment_phase_statistics(stats, times, f, h), phase)
                evidence, _ = profile_track_evidence(
                    stats, times, f, h, phase, beta, phase, study.sigma[selected]
                )
                # Frequency clutter plus unchanged hardware constants, with zero
                # candidate phase: the explicit no-signal alternative.
                parts = evidence["parts"]
                clutter = sum(min(len(t["times"]), 50) * 900**2 for t in tracks)
                clutter += parts["drift_penalty"] + parts["hardware_dimension_penalty"]
                saved.append(dict(
                    phase_s=float(value), score=evidence["score"],
                    all_clutter_score=clutter,
                    supported_points=evidence["compatible_curved_points"],
                    supporting_members=[k for k, ok in zip(keys, evidence["component_supported"],
                                                         strict=True) if ok],
                ))
            profiles[norad] = saved
            write(folder / f"profile_{norad}.json", saved)
            print(json.dumps(dict(arm=arm, norad=norad, best=choose_state(saved, 15))), flush=True)
        labels = {r["component"]: r["candidate_norad"]
                  for r in old["association"]["rows"] if r["compatible"]}
        old_ids = set(old["associated_observation_ids"])
        cache = {}
        for cap in CAPS:
            after = dict(fit, phases_s=list(fit["phases_s"]))
            updates = []
            fixed = dict(labels)
            for norad, profile in profiles.items():
                j = int(np.flatnonzero(study.sky["norad"] == norad)[0])
                state = choose_state(profile, max(float(study.bounds[j]), cap))
                if state:
                    after["phases_s"][j] = state["phase_s"]
                    fixed.update({k: norad for k in state["supporting_members"]})
                    updates.append(dict(norad=norad, **state))
            signature = tuple((r["norad"], r["phase_s"]) for r in updates)
            if signature not in cache:
                result = population_association(Bound(study, fixed), after,
                                                load_tracks(recording), background)
                new_ids = set(result["associated_observation_ids"])
                assert old_ids <= new_ids <= raw_ids
                # The population helper counts the original Graph partition,
                # which omits 310 raw GLRT. Preserve that count separately and
                # explicitly include every raw point in this report's denominator.
                result["original_graph_points"] = result["original_points"]
                result["original_points"] = len(raw_ids)
                result["raw_without_retained_polynomial"] = len(raw_ids) - result["curve_points"]
                result["compatible_fraction_of_original"] = len(new_ids) / len(raw_ids)
                result["unassociated_observation_ids"] = sorted(raw_ids - new_ids)
                cache[signature] = result
                write(folder / f"association_cap_{cap:g}.json", result)
                write(folder / f"fit_cap_{cap:g}.json", after)
            result = cache[signature]
            summaries.append(dict(
                arm=arm, phase_bound_floor_s=cap, associated=result["compatible_points"],
                unassociated=result["original_points"] - result["compatible_points"],
                percent_associated=100 * result["compatible_fraction_of_original"],
                gained=result["compatible_points"] - len(old_ids),
                merged_tracks=result["merged_tracks"], updates=updates,
            ))
        distribution = []
        for norad in sorted(locked):
            rs = [r for r in old["association"]["rows"]
                  if r["compatible"] and r["candidate_norad"] == norad]
            if not any(r["active_curvature"] for r in rs):
                continue
            j = fit["phase_norads"].index(norad)
            distribution.append(dict(norad=norad, phase_s=fit["phases_s"][j],
                                     points=sum(r["points"] for r in rs),
                                     curved_points=sum(r["points"] for r in rs
                                                       if r["active_curvature"])))
        distributions[arm] = distribution
    write(OUTPUT / "summary.json", summaries)
    write(OUTPUT / "phase_distribution.json", distributions)
    write(OUTPUT / "protocol.json", dict(
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        baseline=str(CURRENT.relative_to(ROOT)), candidates=1707, raw_points=4797,
        common_nominations=families, common_grid_s=[-15, 15, 0.05],
        minimum_curved_support=2, all_nominees_costed_including_clutter=True,
        fixed_hardware_and_established_phases=True, fixed_old_labels=True,
        original_phase_priors_unchanged=True, linear_not_used_for_phase_learning=True,
        phase_limit_semantics="max(original per-candidate bound, swept floor) for new families",
        new_identities_provisional_pending_full_bank_competition=True,
        pooled_noise_whiteness_not_established=True,
        known_position_fixed=True, localization_accuracy_claim=False,
    ))
    render(distributions, summaries)
    render_unassociated(raw, summaries)


def render(distributions, summaries):
    rows = distributions["fitted_c"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    phases = [r["phase_s"] for r in rows]
    axes[0].hist(phases, bins=np.arange(-4, 1.76, 0.5), color="steelblue", edgecolor="white")
    axes[0].set(xlabel="Satellite along-track correction (seconds)", ylabel="Satellites",
                title=f"Established curved-supported phases ({len(rows)} satellites)")
    axes[0].axvline(0, color="black", lw=1)
    ordered = sorted(rows, key=lambda r: r["phase_s"])
    axes[1].barh([str(r["norad"]) for r in ordered], [r["phase_s"] for r in ordered],
                 color=["steelblue" if r["phase_s"] < 0 else "darkorange" for r in ordered])
    axes[1].axvline(-2.7, color="purple", ls="--", label="Proposed 63474: −2.70 s")
    axes[1].axvline(0, color="black", lw=1)
    axes[1].set(xlabel="Along-track correction (seconds)", ylabel="NORAD")
    axes[1].legend(fontsize=8)
    fig.suptitle("DSX01 S01 — fitted-c calibration; unsupported candidate phases excluded")
    fig.savefig(OUTPUT / "phase_distribution.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for arm, style in (("c0", "o-"), ("fitted_c", "x--")):
        rs = [r for r in summaries if r["arm"] == arm]
        x = [r["phase_bound_floor_s"] for r in rs]
        axes[0].plot(x, [r["unassociated"] for r in rs], style, label=arm)
        axes[1].plot(x, [r["percent_associated"] for r in rs], style, label=arm)
    axes[0].set(ylabel="Unassociated raw GLRT points", ylim=(0, 2700))
    axes[1].set(ylabel="Associated raw GLRT points (%)", ylim=(0, 100))
    for ax in axes:
        ax.set(xlabel="Phase-bound floor for new families (± seconds)")
        ax.grid(alpha=0.25)
        ax.legend()
    fig.suptitle("DSX01 S01 — phase-range sensitivity, unchanged residual gates\n"
                 "Established phases frozen; gains are provisional individual-fragment matches")
    fig.savefig(OUTPUT / "phase_range_sensitivity.png", dpi=170)
    plt.close(fig)


def render_unassociated(raw, summaries):
    folder = OUTPUT / "fitted_c"
    variants = [
        ("Original phase bounds", "association_cap_0.json"),
        ("Bound floor ±1 s", "association_cap_1.json"),
        ("Bound floor ±2.7…15 s", "association_cap_2.7.json"),
    ]
    original = set(json.loads((folder / variants[0][1]).read_text())["associated_observation_ids"])
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), sharex=True, sharey=True,
                             layout="constrained")
    for row, (label, filename) in enumerate(variants):
        result = json.loads((folder / filename).read_text())
        admitted = set(result["associated_observation_ids"])
        for rx in (1, 2):
            ax = axes[row, rx - 1]
            remaining = [r for r in raw if r["receiver"] == rx
                         and r["observation_id"] not in admitted]
            gained = [r for r in raw if r["receiver"] == rx
                      and r["observation_id"] in admitted - original]
            ax.scatter([r["time_s"] for r in remaining],
                       [r["measured_cfo_hz"] / 1000 for r in remaining],
                       c=[r["channel"] for r in remaining], cmap="tab10", vmin=1, vmax=10,
                       s=6, alpha=0.7, linewidths=0)
            ax.scatter([r["time_s"] for r in gained],
                       [r["measured_cfo_hz"] / 1000 for r in gained],
                       c="limegreen", marker="x", s=12, linewidths=0.7,
                       label="Newly explained")
            ax.set(title=f"{label} · RX{rx} · {len(remaining):,} remaining",
                   xlabel="Seconds from scan start", ylabel="Measured GLRT CFO (kHz)")
            ax.grid(alpha=0.15)
            if gained:
                ax.legend(fontsize=8)
    fig.suptitle("DSX01 S01 — unassociated GLRT as phase range expands\n"
                 "All eight channels; green crosses show provisional newly explained points")
    fig.savefig(OUTPUT / "unassociated_phase_comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    run()
