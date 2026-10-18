"""Bounded independent-position refinement using whole-track-feasible evidence."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from evaluate_robust_curve_reassociation import population_association
from evaluate_shared_satellite_phase import Experiment, protocol
from localize_merged_track_catalogue import distance_km

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.track_evidence_objective import (
    feasible_track_candidates,
    improve_track_evidence,
    profile_track_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "reports/2026_10_17_robust_curve_reassociation"


class EvidenceExperiment(Experiment):
    """Legacy solutions generate proposals; only noise-gated evidence ranks them."""

    def set_blind_seed(self, seed):
        common = np.asarray(seed["beta"][:8], float)
        common[4:8] = np.clip(common[4:8], -150, 150)
        self.initial = np.r_[common, 0.0] if self.fitted_c else common.copy()
        self.seed_phase = np.asarray(seed["phases_s"], float)
        self.seed_geometry = prepare_phase_geometry(self.sky, self.times, self.seed_phase)

    def tangent(self, geometry, latitude, longitude, anchor):
        f, e, h = phase_linear_frequency(geometry, latitude, longitude)
        return self.statistics(f, e, h, anchor=anchor), f, h

    def refine(self, stats, f, h, anchor, beta, phases):
        return improve_track_evidence(
            stats,
            self.times,
            f,
            h,
            anchor,
            beta,
            phases,
            self.sigma,
            self.bounds,
            rounds=2,
            drift_sigma_hz_s=self.drift_sigma_hz_s,
            drift_bound_hz_s=self.drift_bound_hz_s,
        )

    def exact_refine(self, latitude, longitude, beta, phases):
        best, history = None, []
        for iteration in range(4):
            geometry = prepare_phase_geometry(self.sky, self.times, phases)
            stats, f, h = self.tangent(geometry, latitude, longitude, phases)
            evidence, _ = profile_track_evidence(
                stats,
                self.times,
                f,
                h,
                phases,
                beta,
                phases,
                self.sigma,
                drift_sigma_hz_s=self.drift_sigma_hz_s,
            )
            state = dict(evidence=evidence, beta=beta.copy(), phases_s=phases.copy())
            history.append(dict(iteration=iteration, score=evidence["score"]))
            if best is None or evidence["score"] < best["evidence"]["score"]:
                best = state
            if iteration == 3:
                break
            trial = self.refine(stats, f, h, phases, beta, phases)
            if (
                np.max(np.abs(trial["beta"] - beta)) < 0.05
                and np.max(np.abs(trial["phases_s"] - phases)) < 1e-4
            ):
                break
            beta, phases = trial["beta"], trial["phases_s"]
        best["exact_history"] = history
        return best

    def fit(self, latitude, longitude, budget, *, exact=False):
        legacy = super().fit(latitude, longitude, budget, exact=False)
        stats, f, h = self.tangent(self.seed_geometry, latitude, longitude, self.seed_phase)
        proposals = []
        for beta, phases in (
            (self.initial, self.seed_phase),
            (np.asarray(legacy["beta"]), np.asarray(legacy["phases_s"])),
        ):
            result = self.refine(stats, f, h, self.seed_phase, beta, phases)
            if exact:
                result = self.exact_refine(latitude, longitude, result["beta"], result["phases_s"])
            proposals.append(result)
        winner = min(proposals, key=lambda r: r["evidence"]["score"])
        return dict(
            latitude_deg=latitude,
            longitude_deg=longitude,
            score=winner["evidence"]["score"],
            beta=winner["beta"].tolist(),
            phases_s=winner["phases_s"].tolist(),
            phase_norads=self.sky["norad"].tolist(),
            fitted_c=self.fitted_c,
            phase_enabled=True,
            exact_phase_geometry=exact,
            score_parts=winner["evidence"]["parts"],
            compatible_curved_points=winner["evidence"]["compatible_curved_points"],
            compatible_curved_components=winner["evidence"]["compatible_curved_components"],
            tangent_proposals=2,
            legacy_generated_seed_budget=budget,
            legacy_solution_is_proposal_only=True,
            exact_history=winner.get("exact_history", []),
            drift_sigma_hz_s=self.drift_sigma_hz_s,
            drift_bound_hz_s=self.drift_bound_hz_s,
        )

    def associate(self, fit, *, fixed_labels=None):
        """Associate frozen parameters, optionally preserving vetted family labels.

        A requested label still has to pass every frequency and support gate.
        This port estimates no hardware or phase parameter from linear tracks.
        """
        fixed_labels = {} if fixed_labels is None else dict(fixed_labels)
        lookup = {int(n): j for j, n in enumerate(self.sky["norad"])}
        if not set(fixed_labels) <= {t["key"] for t in self.tracks}:
            raise ValueError("fixed label refers to unknown fragment")
        if not set(fixed_labels.values()) <= lookup.keys():
            raise ValueError("fixed label refers to unknown candidate")
        times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        phases, beta = np.asarray(fit["phases_s"]), np.asarray(fit["beta"])
        f, e = phase_frequency_grid(
            self.sky, times, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases
        )
        stats = matching.statistics(
            [(t["key"], [t]) for t in self.tracks],
            dict(time_s=times, doppler_0=f, elevation_deg=e),
            {str(t["channel"]): 0.0 for t in self.tracks},
        )
        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)

        def residual(fi, candidates):
            track, g = self.tracks[fi], stats["g"][fi]
            hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
            if len(beta) == 9:
                hardware += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            ix = np.searchsorted(times, track["times"])
            r = track["values"][None, :] - hardware - track["rf_hz"] / 11.5e9 * f[candidates][:, ix]
            r += terms.aliases[fi, candidates, None] * matching.PERIOD
            r -= terms.bias_hz[fi, candidates, None]
            return r

        feasible = feasible_track_candidates(stats, terms, residual)
        chosen = np.argmin(np.where(feasible, terms.score, np.inf), axis=1)
        rows = []
        for fi, track in enumerate(self.tracks):
            # Retain an explicit diagnostic nomination even when none passes.
            j = (
                lookup[fixed_labels[track["key"]]]
                if track["key"] in fixed_labels
                else chosen[fi]
                if np.any(feasible[fi])
                else terms.best[fi]
            )
            r = residual(fi, np.array([j]))[0]
            rows.append(
                dict(
                    component=track["key"],
                    candidate_norad=int(self.sky["norad"][j]),
                    phase_s=float(phases[j]),
                    points=len(track["times"]),
                    rms_hz=float(np.sqrt(np.mean(r**2))),
                    bias_hz=float(terms.bias_hz[fi, j]),
                    compatible=bool(feasible[fi, j]),
                    active_curvature=track["key"] in self.curved_keys,
                    residual_diagnostics=matching.noise_screen(r, track["times"]),
                    candidates_passing_all_frequency_gates=int(feasible[fi].sum()),
                )
            )
        group_support, satellite_support = np.zeros(4, int), {}
        for track, row in zip(self.tracks, rows, strict=True):
            if row["compatible"] and row["active_curvature"]:
                group_support[matching.group(track)] += 1
                n = row["candidate_norad"]
                satellite_support[n] = satellite_support.get(n, 0) + 1
        for track, row in zip(self.tracks, rows, strict=True):
            row["frequency_compatible_before_calibration_support"] = row["compatible"]
            row["qualified_curved_hardware_support"] = int(group_support[matching.group(track)])
            row["qualified_curved_satellite_support"] = satellite_support.get(
                row["candidate_norad"], 0
            )
            row["compatible"] &= row["qualified_curved_hardware_support"] > 0
            if abs(row["phase_s"]) > 1e-3:
                row["compatible"] &= row["qualified_curved_satellite_support"] > 0
        return dict(
            points=sum(len(t["times"]) for t in self.tracks),
            fragments=len(self.tracks),
            compatible_points=sum(r["points"] for r in rows if r["compatible"]),
            compatible_fragments=sum(r["compatible"] for r in rows),
            rows=rows,
            candidate_selection_after_all_frequency_gates=True,
            independent_identity_truth=False,
        )


def prepare(case, fitted_c):
    recording = (
        ROOT
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
        / case
    )
    inputs = (
        ROOT / "reports/2026_10_17_dsx01_polynomial_satellite_dive/frozen_inputs/DSX01-S01"
        if case.startswith("DSX")
        else PRIOR / "frozen_inputs" / case
    )
    seed_root = PRIOR / ("resumed" if case.startswith("DSX") else "fits") / case / "repaired_c0"
    seed_path = seed_root / "fit.json"
    seed_protocol = json.loads((seed_root / "protocol.json").read_text())
    if seed_protocol["evaluation_position_used_in_search"]:
        raise ValueError("seed protocol used an evaluation coordinate")
    study = EvidenceExperiment(
        recording,
        inputs,
        fitted_c=fitted_c,
        phase_enabled=True,
        drift_sigma_hz_s=0.5,
        drift_bound_hz_s=1.0,
    )
    if seed_protocol["bank_receipt"]["bank_sha256"] != study.receipt["bank_sha256"]:
        raise ValueError("seed used a different causal candidate bank")
    partition = PRIOR / "partition" / case
    receipt = json.loads((partition / "receipt.json").read_text())
    if receipt["original_tracks_sha256"] != study.receipt["tracks_sha256"]:
        raise ValueError("partition has a different original population")
    for name in ("curves", "background"):
        if (
            hashlib.sha256((partition / f"{name}.json").read_bytes()).hexdigest()
            != receipt[f"{name}_sha256"]
        ):
            raise ValueError("partition payload changed")
    curves = json.loads((partition / "curves.json").read_text())
    for t in curves:
        t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
    background = json.loads((partition / "background.json").read_text())
    binding = study.set_observation_partition(curves, [r["observation_id"] for r in background])
    seed = json.loads(seed_path.read_text())["endpoint"]
    study.set_blind_seed(seed)
    return study, seed, seed_path, binding, recording, background


def conditional_intercept_nulls(study, fit, repetitions=16):
    """Frozen-state diagnostics preserving each curve's times and centered shape.

    Random native intercepts break agreement with learned common hardware while
    leaving slopes, curvature, noise and alias branches up to a constant intact.
    No model refits or geographic search occur. This is not an identity FDR.
    """
    phases, beta = np.asarray(fit["phases_s"]), np.asarray(fit["beta"])
    geometry = prepare_phase_geometry(study.sky, study.times, phases)
    stats, f, h = study.tangent(geometry, fit["latitude_deg"], fit["longitude_deg"], phases)
    actual, _ = profile_track_evidence(
        stats,
        study.times,
        f,
        h,
        phases,
        beta,
        phases,
        study.sigma,
        drift_sigma_hz_s=study.drift_sigma_hz_s,
    )
    rng, rows = np.random.default_rng(271828), []
    period = 1 / 4.4e-6
    for repetition in range(repetitions):
        shifts = rng.uniform(-period / 2, period / 2, len(stats["fragments"]))
        fragments = [
            dict(t, values=t["values"] + shift)
            for t, shift in zip(stats["fragments"], shifts, strict=True)
        ]
        randomized = dict(stats, mean=stats["mean"] + shifts[:, None], fragments=fragments)
        evidence, _ = profile_track_evidence(
            randomized,
            study.times,
            f,
            h,
            phases,
            beta,
            phases,
            study.sigma,
            drift_sigma_hz_s=study.drift_sigma_hz_s,
        )
        rows.append(
            dict(
                repetition=repetition,
                score=evidence["score"],
                compatible_curved_points=evidence["compatible_curved_points"],
            )
        )
    return dict(
        actual=actual,
        nulls=rows,
        seed=271828,
        randomized_intercept_width_hz=period,
        parameters_frozen=True,
        times_centered_shapes_and_rf_preserved=True,
        c0_and_fitted_c_same_random_shifts=True,
        null_not_reoptimized=True,
        calibrated_false_discovery_rate=False,
    )


def locate(study, seed, output):
    center_lat, center_lon = study.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(center_lat))
    start = np.array(
        [(seed["longitude_deg"] - center_lon) * scale, (seed["latitude_deg"] - center_lat) * 111]
    )
    cache, trace = {}, []

    def evaluate(point):
        key = tuple(np.round(point, 9))
        if key not in cache:
            if len(cache) >= 41 or np.linalg.norm(point) > study.receipt["radius_km"]:
                return np.inf
            started = time.monotonic()
            fit = study.fit(center_lat + point[1] / 111, center_lon + point[0] / scale, 4)
            cache[key] = fit
            trace.append(
                dict(
                    east_north_km=list(key),
                    score=fit["score"],
                    curved_points=fit["compatible_curved_points"],
                    elapsed_seconds=time.monotonic() - started,
                )
            )
            write(output / "progress.json", trace)
            if len(trace) % 4 == 0:
                print(
                    json.dumps(
                        dict(
                            stage="noise_gated_search",
                            locations=len(trace),
                            best_score=min(r["score"] for r in trace),
                        )
                    ),
                    flush=True,
                )
        return cache[key]["score"]

    grid = [start + np.array([x, y]) for x in (-16, 0, 16) for y in (-16, 0, 16)]
    point = min(grid, key=evaluate).copy()
    value = evaluate(point)
    for step in (8.0, 2.0, 0.5, 0.125):
        for _ in range(2):
            neighbors = [point + step * np.array(d) for d in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            trial = min(neighbors, key=evaluate)
            proposed = evaluate(trial)
            if proposed >= value:
                break
            point, value = trial.copy(), proposed
    finalists = []
    for row in sorted(trace, key=lambda r: r["score"]):
        xy = np.asarray(row["east_north_km"])
        if all(np.linalg.norm(xy - np.asarray(r["east_north_km"])) >= 0.5 for r in finalists):
            fit = study.fit(center_lat + xy[1] / 111, center_lon + xy[0] / scale, 8, exact=True)
            finalists.append(dict(east_north_km=xy.tolist(), fit=fit))
            write(output / "finalists.json", finalists)
        if len(finalists) == 3:
            break
    best = min(finalists, key=lambda r: r["fit"]["score"])
    result = dict(
        endpoint=best["fit"],
        finalists=finalists,
        east_north_km=best["east_north_km"],
        initial_east_north_km=start,
        local_locations=len(trace),
        resumed_blind_not_cold=True,
        evaluation_position_used_in_search=False,
        global_optimum_proven=False,
    )
    write(output / "fit.json", result)
    return result


def run(case, fitted_c, output, *, smoke=False):
    study, seed, seed_path, binding, recording, background = prepare(case, fitted_c)
    protocol(study, output, "noise_gated_evidence_blind_refinement", 8)
    write(
        output / "evidence_protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            objective_sha256=hashlib.sha256(
                (ROOT / "src/leo/analysis/research/track_evidence_objective.py").read_bytes()
            ).hexdigest(),
            seed_fit_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            seed_protocol_sha256=hashlib.sha256(
                seed_path.with_name("protocol.json").read_bytes()
            ).hexdigest(),
            partition=binding,
            same_blind_c0_seed_for_both_c_arms=True,
            only_curved_fragments_rank_or_update_parameters=True,
            grid_offsets_km=[-16, 0, 16],
            local_steps_km=[8, 2, 0.5, 0.125],
            maximum_sweeps_per_step=2,
            maximum_locations=41,
            exact_finalists=3,
            discovery_legacy_seed_budget=4,
            exact_legacy_seed_budget=8,
            legacy_objective_used_only_for_proposals=True,
            c0_fitted_c_points_candidates_priors_and_budgets_matched=True,
            no_known_position_parameters_or_phases_used=True,
            no_points_withheld=True,
            smoke_only=smoke,
        ),
    )
    started = time.monotonic()
    if smoke:
        fit = study.fit(seed["latitude_deg"], seed["longitude_deg"], 4, exact=True)
        write(output / "smoke_fit.json", fit)
        print(
            json.dumps(
                dict(
                    elapsed_seconds=time.monotonic() - started,
                    score=fit["score"],
                    curved_points=fit["compatible_curved_points"],
                )
            ),
            flush=True,
        )
        return
    result = locate(study, seed, output)
    digest = hashlib.sha256((output / "fit.json").read_bytes()).hexdigest()
    association = population_association(
        study, result["endpoint"], load_tracks(recording), background
    )
    write(output / "association.json", association)
    # Reference coordinates enter only after the independent endpoint is saved.
    reference = (37.849061591561885, -122.48574968092912)
    error = distance_km(
        (result["endpoint"]["latitude_deg"], result["endpoint"]["longitude_deg"]), reference
    )
    write(
        output / "evaluation.json",
        dict(
            position_error_km=error,
            within_0_5km=error < 0.5,
            reference_used_only_after_fit=True,
            fit_sha256=digest,
            resumed_not_cold=True,
        ),
    )
    write(output / "conditional_nulls.json", conditional_intercept_nulls(study, result["endpoint"]))
    summary = dict(
        case=case,
        fitted_c=fitted_c,
        position_error_km=error,
        associated_points=association["compatible_points"],
        merged_tracks=association["merged_tracks"],
        curved_points=result["endpoint"]["compatible_curved_points"],
        original_graph_points=association["original_points"],
        background_points=len(background),
        locations=result["local_locations"],
        score=result["endpoint"]["score"],
        elapsed_seconds=time.monotonic() - started,
    )
    write(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DSX01-S01", "DS22-001"), required=True)
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.fitted_c, a.output, smoke=a.smoke)
