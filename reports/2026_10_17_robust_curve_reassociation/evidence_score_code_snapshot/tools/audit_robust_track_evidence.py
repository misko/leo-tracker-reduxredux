"""Compare residual-aware evidence on saved states; never seed location from GPS."""

import hashlib
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from evaluate_shared_satellite_phase import Experiment

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import penalized_score, profile_phases
from leo.analysis.research.track_evidence_objective import score_track_evidence

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_17_robust_curve_reassociation"
DEEP = ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive"


def score_state(study, fit):
    phase, beta = np.asarray(fit["phases_s"]), np.asarray(fit["beta"])
    geometry = prepare_phase_geometry(study.sky, study.times, phase)
    f, e, h = phase_linear_frequency(geometry, fit["latitude_deg"], fit["longitude_deg"])
    stats = study.statistics(f, e, h, anchor=phase)
    terms = profile_phases(stats, beta, phase)

    def residuals(fi, candidates):
        track = stats["fragments"][fi]
        ci = stats["ci"][fi]
        ix = np.searchsorted(study.times, track["times"])
        g = matching.group(track)
        hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
        r = track["values"][None, :] - hardware[None, :]
        r = r - track["rf_hz"] / 11.5e9 * f[candidates][:, ix]
        r += terms.aliases[fi, candidates, None] * matching.PERIOD
        r -= terms.bias_hz[ci, candidates, None]
        if not np.allclose(
            np.mean(r * r, axis=1), terms.residual_mse[ci, candidates], rtol=1e-7, atol=0.01
        ):
            raise ValueError("pointwise and profiled component residuals disagree")
        return r

    result = score_track_evidence(
        stats, terms, beta, phase, study.sigma, residuals, drift_sigma_hz_s=study.drift_sigma_hz_s
    )
    legacy, _, parts = penalized_score(
        stats, beta, phase, study.sigma, drift_sigma_hz_s=study.drift_sigma_hz_s
    )
    result.update(
        legacy_score=legacy,
        legacy_parts=parts,
        selected_norads=[
            int(study.sky["norad"][j]) if j >= 0 else None
            for j in result["selected_candidate_indexes"]
        ],
    )
    return result


def make_study(case, arm, repaired):
    recording = (
        ROOT
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
        / case
    )
    inputs = (
        DEEP / "frozen_inputs/DSX01-S01"
        if case == "DSX01-S01"
        else Path("/tmp") / f"ds22-shared-phase-bank-{case}"
    )
    study = Experiment(
        recording,
        inputs,
        fitted_c=arm == "fitted_c",
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1,
    )
    background = []
    if repaired:
        partition = REPORT / "partition" / case
        cores = json.loads((partition / "curves.json").read_text())
        for t in cores:
            t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
        background = json.loads((partition / "background.json").read_text())
        study.set_observation_partition(cores, [r["observation_id"] for r in background])
    return study, recording, background


def run():
    output = REPORT / "track_evidence_audit"
    output.mkdir(exist_ok=False)
    summaries, lineage = [], {}
    for case in ("DSX01-S01", "DSX01-S02", "DS22-001"):
        populations = (True,) if case == "DSX01-S02" else (False, True)
        for repaired in populations:
            variant = "repaired" if repaired else "original"
            for arm in ("c0", "fitted_c"):
                study, recording, background = make_study(case, arm, repaired)
                own = output / case / f"{variant}_{arm}"
                own.mkdir(parents=True)
                if case == "DSX01-S02":
                    baseline_path = DEEP / "cohort" / case / arm / "diagnosis.json"
                    baseline = json.loads(baseline_path.read_text())[0]["fit"]
                    raw_path = REPORT / "fixed_cohort" / case / arm / "fit.json"
                    states = dict(
                        original_parameters=baseline, raw_refit=json.loads(raw_path.read_text())
                    )
                    paths = [baseline_path, raw_path]
                else:
                    root = REPORT / "fits" / case / f"{variant}_{arm}"
                    states = dict(
                        known_position=json.loads((root / "fixed_site.json").read_text())["fit"],
                        cold_blind=json.loads((root / "fit.json").read_text())["endpoint"],
                    )
                    paths = [root / "fixed_site.json", root / "fit.json"]
                    if case.startswith("DSX"):
                        path = REPORT / "resumed" / case / f"{variant}_{arm}" / "fit.json"
                        states["resumed_blind"] = json.loads(path.read_text())["endpoint"]
                        paths.append(path)
                        if repaired:
                            path = REPORT / "fits" / case / f"original_{arm}" / "fixed_site.json"
                            states["original_parameters"] = json.loads(path.read_text())["fit"]
                            paths.append(path)
                for path in paths:
                    lineage[str(path.relative_to(ROOT))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                ranked = []
                for name, fit in states.items():
                    evidence = score_state(study, fit)
                    association = study.associate(fit)
                    write(own / f"{name}.json", evidence)
                    row = dict(
                        case=case,
                        population=variant,
                        arm=arm,
                        state=name,
                        latitude_deg=fit["latitude_deg"],
                        longitude_deg=fit["longitude_deg"],
                        legacy_score=evidence["legacy_score"],
                        track_evidence_score=evidence["score"],
                        compatible_curved_points=evidence["compatible_curved_points"],
                        calibration_points=evidence["total_calibration_points"],
                        associated_all_points=association["compatible_points"],
                    )
                    ranked.append(row)
                    summaries.append(row)
                if repaired and case.startswith("DSX"):
                    # State selection is only at the same known position. Never
                    # compare the GPS state with a blind state to initialize search.
                    names = (
                        ("original_parameters", "raw_refit")
                        if case.endswith("S02")
                        else ("original_parameters", "known_position")
                    )
                    allowed = [r for r in ranked if r["state"] in names]
                    if len({(r["latitude_deg"], r["longitude_deg"]) for r in allowed}) != 1:
                        raise ValueError("known-position safeguard mixes geographic hypotheses")
                    winner = min(allowed, key=lambda r: r["track_evidence_score"])
                    chosen = population_association(
                        study, states[winner["state"]], load_tracks(recording), background
                    )
                    write(own / "safeguarded_fit.json", states[winner["state"]])
                    write(own / "safeguarded_association.json", chosen)
                    write(
                        own / "safeguard.json",
                        dict(
                            selected_state=winner["state"],
                            selected_track_evidence_score=winner["track_evidence_score"],
                            associated_points=chosen["compatible_points"],
                            original_points=chosen["original_points"],
                            background_points=len(background),
                            only_curved_tracks_ranked_states=True,
                            known_position_fixed=True,
                            not_used_as_geographic_initializer=True,
                            parameter_proposals_not_reoptimized=True,
                            compared_states=allowed,
                        ),
                    )
    write(output / "summary.json", summaries)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            objective_source_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/track_evidence_objective.py").read_bytes()
            ).hexdigest(),
            input_states_sha256=lineage,
            only_measured_curved_fragments_rank_states=True,
            every_original_member_noise_check_required=True,
            no_candidate_selected_before_gates=True,
            failed_component_cost="capped-count times 900Hz squared",
            gaussian_bias_phase_drift_and_conditional_volume_penalties_retained=True,
            hardware_dimension_penalty=(
                "150Hz squared times len(beta) times log(calibration points)"
            ),
            c0_fitted_c_same_candidate_states_populations_thresholds_priors_and_budget=True,
            state_pool_audit_only_no_new_position_search=True,
            known_position_state_never_used_as_a_geographic_initializer=True,
            composite_score_not_an_identity_probability=True,
            no_false_discovery_rate_claim=True,
        ),
    )
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    run()
