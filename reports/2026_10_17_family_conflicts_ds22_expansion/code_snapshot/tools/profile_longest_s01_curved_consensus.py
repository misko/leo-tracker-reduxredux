"""Retain every old nominee in a whole-curve signal/clutter phase profile."""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from deep_dive_longest_unassociated_s01 import CURRENT, OUTPUT, TARGET
from evaluate_robust_curve_reassociation import population_association
from inventory_clipped_phase_cohort import ROOT, load_study

from leo.analysis.research.fixed_assignment_fit import common_candidate_phase_scores
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases
from leo.analysis.research.track_evidence_objective import profile_track_evidence

MEMBERS = ["S01-RX1-CH2-T001", "S01-RX1-CH3-T002", TARGET, "S01-RX1-CH7-T001"]
CONSENSUS = ["S01-RX1-CH2-T001", TARGET, "S01-RX1-CH7-T001"]


def run():
    summaries = []
    for fc in (False, True):
        arm = "fitted_c" if fc else "c0"
        study, _, _, recording, background = load_study("DSX01-S01", fc)
        fit = json.loads((CURRENT / arm / "fit.json").read_text())
        old = json.loads((CURRENT / arm / "association.json").read_text())
        mapping = {t["key"]: t for t in study.tracks}
        tracks = [mapping[k] for k in MEMBERS]
        assert all(k in study.curved_keys for k in MEMBERS)
        selected = np.flatnonzero(study.sky["norad"] == 63474)
        sky = {k: study.sky[k][selected] for k in ["position_km", "velocity_km_s"]}
        sky["time_s"] = study.sky["time_s"]
        j = int(selected[0])
        sigma = study.sigma[selected]
        beta = np.array(fit["beta"])
        times = np.unique(np.concatenate([t["times"] for t in tracks]))
        grids = np.linspace(-15, 15, 601)
        saved = []
        transfer = {key: [] for key in CONSENSUS}
        before_curved = {
            r["candidate_norad"]
            for r in old["association"]["rows"]
            if r["compatible"] and r["active_curvature"]
        }
        assert 63474 not in before_curved

        def statistics(subset, f, e, h, phase, times=times):
            stats = matching.statistics(
                [(t["key"], [t]) for t in subset],
                dict(time_s=times, doppler_0=f, elevation_deg=e),
                {str(t["channel"]): 0.0 for t in subset},
            )
            return recenter_phases(augment_phase_statistics(stats, times, f, h), phase)

        for value in grids:
            phase = np.array([value])
            geom = prepare_phase_geometry(sky, times, phase)
            f, e, h = phase_linear_frequency(geom, fit["latitude_deg"], fit["longitude_deg"])
            stats = statistics(tracks, f, e, h, phase)
            evidence, terms = profile_track_evidence(stats, times, f, h, phase, beta, phase, sigma)
            rows = []
            for i, t in enumerate(tracks):
                g = matching.group(t)
                ix = np.searchsorted(times, t["times"])
                hw = beta[g] + beta[g + 4] * (t["times"] - 150) / 150
                if len(beta) == 9:
                    hw += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
                residual = (
                    t["values"]
                    - hw
                    - t["rf_hz"] / 11.5e9 * f[0, ix]
                    + terms.aliases[i, 0] * matching.PERIOD
                    - terms.bias_hz[i, 0]
                )
                noise = matching.noise_screen(residual, t["times"])
                rms = float(np.sqrt(np.mean(residual**2)))
                passes = bool(
                    stats["component_visible"][i, 0]
                    and rms <= 450
                    and abs(terms.bias_hz[i, 0]) <= 3000
                    and noise["noise_screen_pass"]
                )
                rows.append(
                    dict(
                        component=t["key"],
                        points=len(residual),
                        rms_hz=rms,
                        bias_hz=float(terms.bias_hz[i, 0]),
                        passing=passes,
                        residual_hz=residual,
                        diagnostics=noise,
                    )
                )
            saved.append(
                dict(
                    phase_s=float(value),
                    score=evidence["score"],
                    score_parts=evidence["parts"],
                    supported_points=evidence["compatible_curved_points"],
                    rows=rows,
                )
            )
            for omitted in CONSENSUS:
                subset = [mapping[k] for k in CONSENSUS if k != omitted]
                reduced = statistics(subset, f, e, h, phase)
                cost, _ = common_candidate_phase_scores(reduced, beta, phase, sigma)
                feasible = all(
                    r["passing"]
                    for r in rows
                    if r["component"] in CONSENSUS and r["component"] != omitted
                )
                transfer[omitted].append(
                    dict(
                        phase_s=float(value),
                        score=float(cost[0]),
                        anchor_members_passing=feasible,
                        omitted_member=next(r for r in rows if r["component"] == omitted),
                    )
                )
        best = min(saved, key=lambda r: r["score"])
        chosen = best["phase_s"]
        retained = [r["component"] for r in best["rows"] if r["passing"]]
        assert retained == CONSENSUS
        after = dict(fit, phases_s=list(fit["phases_s"]))
        after["phases_s"][j] = chosen
        labels = {
            r["component"]: r["candidate_norad"]
            for r in old["association"]["rows"]
            if r["compatible"]
        }
        labels.update({k: 63474 for k in CONSENSUS})

        class Bound:
            def __init__(self, experiment, fixed):
                self.experiment, self.fixed = experiment, fixed
                self.tracks, self.sky = experiment.tracks, experiment.sky

            def associate(self, fit):
                return self.experiment.associate(fit, fixed_labels=self.fixed)

        result = population_association(
            Bound(study, labels), after, load_tracks(recording), background
        )
        oldids = set(old["associated_observation_ids"])
        newids = set(result["associated_observation_ids"])
        assert oldids <= newids
        diagnostics = []
        for omitted, states in transfer.items():
            best_transfer = min(
                (r for r in states if r["anchor_members_passing"]), key=lambda r: r["score"]
            )
            diagnostics.append(
                dict(
                    omitted_member=omitted,
                    phase_s=best_transfer["phase_s"],
                    omitted_member_passing=best_transfer["omitted_member"]["passing"],
                    omitted_member_rms_hz=best_transfer["omitted_member"]["rms_hz"],
                )
            )
        folder = OUTPUT / arm / "curved_consensus"
        folder.mkdir()
        write(folder / "phase_profile.json", saved)
        write(folder / "selected_phase.json", best)
        write(folder / "transfer_diagnostics.json", diagnostics)
        write(folder / "fit.json", after)
        write(folder / "association.json", result)
        write(
            folder / "protocol.json",
            dict(
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                candidate_norad=63474,
                all_original_nominees=MEMBERS,
                all_nomination_points=sum(len(t["times"]) for t in tracks),
                whole_curve_clutter_retained_in_score=True,
                linear_tracks_excluded_from_calibration=True,
                original_gaussian_phase_prior_preserved=True,
                phase_sigma_s=float(sigma[0]),
                original_phase_box_s=float(study.bounds[j]),
                profile_box_s=[-15, 15],
                grid_points=601,
                hardware_and_old_curved_supported_phases_frozen=True,
                full_bank_uniqueness_witness=str(
                    (OUTPUT / arm / "phase_grid.npz").relative_to(ROOT)
                ),
                joint_family_uniqueness_follows_from_target_must_pass_same_grid=True,
                every_original_graph_point_accounted_for=result[
                    "all_original_points_accounted_for"
                ],
                supplied_position_fixed=True,
                no_geographic_accuracy_claim=True,
            ),
        )
        summary = dict(
            arm=arm,
            norad=63474,
            phase_s=chosen,
            retained_curved=retained,
            retained_curved_points=sum(r["points"] for r in best["rows"] if r["passing"]),
            explicit_clutter_nominees=[r["component"] for r in best["rows"] if not r["passing"]],
            before_points=len(oldids),
            after_points=len(newids),
            gained_points=len(newids - oldids),
            lost_points=len(oldids - newids),
            percent_raw=100 * len(newids) / 4797,
            merged_tracks=result["merged_tracks"],
            transfer_diagnostics=diagnostics,
        )
        write(folder / "summary.json", summary)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    write(OUTPUT / "consensus_summary.json", summaries)


if __name__ == "__main__":
    run()
