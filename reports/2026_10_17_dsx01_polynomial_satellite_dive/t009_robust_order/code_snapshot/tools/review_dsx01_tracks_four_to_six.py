"""Review S01 T005/T000/T012 with curved-only phase transfer and a counterfactual.

Hardware remains frozen. Short fragments never select a usable calibration.
The unsupported-family phase fit is explicitly a counterfactual, not admission.
"""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from review_dsx01_selected_track_joins import evaluate_join

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid

ROOT = Path(__file__).resolve().parents[1]
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"


def choose_anchor_phase(phases, anchor_cost, counts, active_curvature, sigma_s):
    """Choose a phase using only qualified measured-curved anchor likelihoods.

    Gaussian constant profile costs are in Hz^2/point. Fragment effective counts
    are capped at 50, matching the existing discovery score. A prior is charged
    once per satellite. This diagnostic does not recompute the full conditional
    phase-volume penalty or other satellites' assignments.
    """
    phases, costs = np.asarray(phases), np.asarray(anchor_cost)
    counts, curved = np.asarray(counts), np.asarray(active_curvature, bool)
    if costs.shape != (len(phases), len(counts)) or curved.shape != counts.shape:
        raise ValueError("matching phase/anchor arrays required")
    if sigma_s <= 0 or not np.isfinite(sigma_s):
        raise ValueError("finite positive phase prior sigma required")
    if not curved.any():
        return None, None
    weights = np.minimum(counts[curved], 50)
    score = np.sum(weights[None, :] * costs[:, curved], axis=1) / 150**2
    score += (phases / sigma_s) ** 2
    return int(np.argmin(score)), score


def summarize_track(track, frequency, terms, fi, beta):
    g, q = matching.group(track), track["rf_hz"] / 11.5e9
    hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
    if len(beta) == 9:
        hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
    residual = track["values"] + terms.aliases[fi, 0] * matching.PERIOD - hardware
    residual -= q * frequency + terms.bias_hz[fi, 0]
    noise = matching.noise_screen(residual, track["times"])
    x = track["times"] - track["times"].mean()
    return dict(
        component=track["key"],
        points=len(residual),
        rms_hz=float(terms.rms_hz[fi]),
        bias_hz=float(terms.bias_hz[fi, 0]),
        residual_slope_hz_s=float(residual @ x / (x @ x)),
        noise=noise,
        numerical_gates_pass=bool(
            terms.rms_hz[fi] <= 450
            and abs(terms.bias_hz[fi, 0]) <= 3000
            and noise["noise_screen_pass"]
        ),
    )


def phase_profile(norad, tracks, mapping, rows, sky, fit, phases, output):
    j = int(np.flatnonzero(sky["norad"] == norad)[0])
    if norad == 64936:
        family = [t for t in tracks if rows[t["key"]]["candidate_norad"] == norad]
        family_keys = {t["key"] for t in family}
        selected = [
            t for t in tracks if rows[t["key"]]["active_curvature"] or t["key"] in family_keys
        ]
        anchors = []
    else:
        target = "S01-RX1-CH1-" + ("T005" if norad == 69433 else "T000")
        anchors = [
            t
            for t in tracks
            if t["key"] != target
            and rows[t["key"]]["compatible"]
            and rows[t["key"]]["active_curvature"]
            and rows[t["key"]]["candidate_norad"] == norad
        ]
        family = [mapping[target]]
        selected = sorted([*anchors, *family], key=lambda t: t["key"])
    if norad == 64936 and any(rows[t["key"]]["active_curvature"] for t in family):
        raise ValueError("counterfactual family unexpectedly contains a curved anchor")
    times = np.unique(np.concatenate([t["times"] for t in selected]))
    beta = np.asarray(fit["beta"])
    sub = dict(
        time_s=sky["time_s"],
        position_km=sky["position_km"][[j]],
        velocity_km_s=sky["velocity_km_s"][[j]],
    )
    records, anchor_scores, family_scores = [], [], []
    for phase in phases:
        frequency, elevation = phase_frequency_grid(
            sub,
            times,
            fit["latitude_deg"],
            fit["longitude_deg"],
            phase_seconds=phase,
        )
        stats = matching.statistics(
            [(t["key"], [t]) for t in selected],
            dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
            {str(t["channel"]): 0.0 for t in selected},
        )
        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)
        member_rows, curve_hits = [], []
        for fi, t in enumerate(selected):
            ix = np.searchsorted(times, t["times"])
            record = summarize_track(t, frequency[0, ix], terms, fi, beta)
            record["visible"] = bool(stats["component_visible"][fi, 0])
            record["numerical_gates_pass"] &= record["visible"]
            member_rows.append(record)
            if rows[t["key"]]["active_curvature"] and record["numerical_gates_pass"]:
                curve_hits.append(t["key"])
        key_index = {t["key"]: i for i, t in enumerate(selected)}
        anchor_scores.append([terms.score[key_index[t["key"]], 0] for t in anchors])
        if norad == 64936:
            group = matching.statistics(
                [("family", family)],
                dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
                {str(t["channel"]): 0.0 for t in family},
            )
            group_terms = profile_component_bias(group, beta, bias_sigma_hz=1000)
            family_scores.append(
                float(
                    group_terms.score[0, 0] * sum(len(t["times"]) for t in family) / 150**2
                    + (phase / sky["phase_sigma_s"][j]) ** 2
                )
            )
        records.append(
            dict(phase_s=float(phase), curved_passing_members=curve_hits, members=member_rows)
        )
    selected_index, scores = choose_anchor_phase(
        phases,
        np.asarray(anchor_scores).reshape(len(phases), len(anchors)),
        [len(t["times"]) for t in anchors],
        np.ones(len(anchors), bool),
        sky["phase_sigma_s"][j],
    )
    selected_record = None if selected_index is None else records[selected_index]
    summary = dict(
        norad=norad,
        phase_sigma_s=float(sky["phase_sigma_s"][j]),
        phase_bound_s=float(sky["phase_bound_s"][j]),
        phase_grid_points=len(phases),
        original_phase_s=float(fit["phases_s"][j]),
        anchor_keys=[t["key"] for t in anchors],
        target_keys=[t["key"] for t in family],
        selected_phase_s=None if selected_record is None else selected_record["phase_s"],
        selected_profile=selected_record,
        curved_tracks_tested=sum(rows[t["key"]]["active_curvature"] for t in selected),
        curved_tracks_passing_any_grid_phase=sorted(
            {k for r in records for k in r["curved_passing_members"]}
        ),
        counterfactual_uses_noncurved_fragments=False,
    )
    if norad == 64936:
        best = int(np.argmin(family_scores))
        phase = phases[best]
        frequency, elevation = phase_frequency_grid(
            sub,
            times,
            fit["latitude_deg"],
            fit["longitude_deg"],
            phase_seconds=phase,
        )
        checked = evaluate_join(
            family,
            times,
            frequency,
            elevation,
            beta,
            np.array([norad]),
            np.array([True]),
            np.ones(4, bool),
        )
        summary.update(
            counterfactual_uses_noncurved_fragments=True,
            counterfactual_phase_s=float(phase),
            counterfactual_shared_constant_check=checked,
            counterfactual_not_a_usable_calibration=True,
        )
    write(
        output / f"phase_profile_{norad}.json",
        dict(
            summary=summary,
            grid=records,
            anchor_only_cost=scores,
            family_counterfactual_cost=family_scores,
        ),
    )
    return summary


def run():
    output = DEEP / "tracks_four_to_six"
    output.mkdir(exist_ok=False)
    recording = ROOT / "reports/2026_10_17_ds22_merged_satellites/dsx01_adapter/DSX01-S01"
    tracks = load_tracks(recording)
    mapping = {t["key"]: t for t in tracks}
    sky = dict(np.load(DEEP / "frozen_inputs/DSX01-S01/bank.npz"))
    studies = {
        arm: json.loads((DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json").read_text())[0]
        for arm in ("c0", "fitted_c")
    }
    nomination_rows = {r["component"]: r for r in studies["fitted_c"]["association"]["rows"]}
    grids = {}
    for norad in (69433, 60372, 64936):
        j = int(np.flatnonzero(sky["norad"] == norad)[0])
        grids[norad] = np.unique(
            np.r_[
                np.linspace(-sky["phase_bound_s"][j], sky["phase_bound_s"][j], 81),
                studies["c0"]["fit"]["phases_s"][j],
                studies["fitted_c"]["fit"]["phases_s"][j],
            ]
        )
    pairs = {
        "T005_curved_peer": ["S01-RX1-CH1-T005", "S01-RX1-CH2-T002"],
        "T000_short_peer": ["S01-RX1-CH1-T000", "S01-RX1-CH3-T008"],
    }
    summaries, hashes = [], {}
    for arm in ("c0", "fitted_c"):
        own = output / arm
        own.mkdir()
        path = DEEP / "cohort/DSX01-S01" / arm / "diagnosis.json"
        raw = json.loads(path.read_text())[0]
        hashes[arm] = hashlib.sha256(path.read_bytes()).hexdigest()
        fit, rows = raw["fit"], {r["component"]: r for r in raw["association"]["rows"]}
        supported, phase_support = np.zeros(4, bool), set()
        for t in tracks:
            if rows[t["key"]]["compatible"] and rows[t["key"]]["active_curvature"]:
                supported[matching.group(t)] = True
                phase_support.add(rows[t["key"]]["candidate_norad"])
        allowed = (np.abs(fit["phases_s"]) <= 1e-3) | np.isin(sky["norad"], list(phase_support))
        times = np.unique(
            np.concatenate([mapping[k]["times"] for keys in pairs.values() for k in keys])
        )
        frequency, elevation = phase_frequency_grid(
            sky,
            times,
            fit["latitude_deg"],
            fit["longitude_deg"],
            phase_seconds=fit["phases_s"],
        )
        for name, keys in pairs.items():
            checked = evaluate_join(
                [mapping[k] for k in keys],
                times,
                frequency,
                elevation,
                np.asarray(fit["beta"]),
                sky["norad"],
                allowed,
                supported,
            )
            write(own / f"{name}.json", checked)
            summaries.append(
                dict(
                    arm=arm,
                    check=name,
                    points=checked["points"],
                    passing_candidates=checked["passing_candidates"],
                    join_favored=checked["join_favored"],
                )
            )
        for norad in (69433, 60372, 64936):
            s = phase_profile(norad, tracks, mapping, nomination_rows, sky, fit, grids[norad], own)
            summaries.append(
                dict(
                    arm=arm,
                    check=f"phase_{norad}",
                    **{
                        k: s[k]
                        for k in (
                            "anchor_keys",
                            "original_phase_s",
                            "selected_phase_s",
                            "curved_tracks_tested",
                            "curved_tracks_passing_any_grid_phase",
                        )
                    },
                )
            )
    write(output / "summary.json", summaries)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            input_fit_sha256=hashes,
            no_hardware_refit=True,
            no_observations_discarded=True,
            short_fragments_excluded_from_usable_phase_selection=True,
            anchor_transfer_is_conditional_on_hardware_fitted_with_reviewed_tracks=True,
            unsupported_family_phase_counterfactual_never_promoted=True,
            anchor_labels_fixed_to_fitted_c_proposals_for_both_arms=True,
            supplied_position_fixed=True,
            geographic_accuracy_not_evaluated=True,
            c0_fitted_c_matched_points_candidates_priors_phase_grids_and_budgets=True,
        ),
    )
    print(json.dumps(summaries, default=lambda v: v.tolist()), flush=True)


if __name__ == "__main__":
    run()
