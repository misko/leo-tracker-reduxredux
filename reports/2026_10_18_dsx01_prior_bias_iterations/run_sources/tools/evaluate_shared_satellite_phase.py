"""Joint hardware/constant-bias solve and one physical phase per candidate NORAD.

Calibration and geographic discovery use every point of individually curved
fragments. All original Graph observations remain in final association. The
reference GPS is excluded from search and used after its fit is sealed.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write
from localize_merged_track_catalogue import distance_km, raw_curvature
from search_merged_track_position import regional_search

from leo.analysis.research.component_frequency_bias import profile_component_bias
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.shared_orbit_phase_fit import (
    augment_phase_statistics,
    joint_update,
    penalized_score,
    profile_phases,
    proposal_phases,
    recenter_phases,
)
from leo.sky.frames import geodetic_to_ecef_km


def clean_info(info):
    if info is None:
        return dict(joint_update_applied=False)
    return dict(
        joint_update_applied=True,
        supported_groups=info["supported_groups"],
        phase_parameters=info["phase_parameters"],
        box_solver_converged=info["box_solver_converged"],
        normal_rank=int(np.linalg.matrix_rank(info["normal_with_priors"])),
        parameters=len(info["normal_with_priors"]),
    )


def improve(
    stats,
    beta,
    phase,
    sigma,
    bounds,
    *,
    gates=(4000.0, 1000.0, 450.0),
    drift_sigma_hz_s=2.0,
    drift_bound_hz_s=5.0,
):
    if not np.isfinite(drift_sigma_hz_s) or drift_sigma_hz_s <= 0:
        raise ValueError("finite positive drift prior sigma required")
    if not np.isfinite(drift_bound_hz_s) or drift_bound_hz_s < 0:
        raise ValueError("finite nonnegative drift bound required")
    beta = beta.copy()
    beta[4:8] = np.clip(beta[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
    score, terms, parts = penalized_score(
        stats, beta, phase, sigma, drift_sigma_hz_s=drift_sigma_hz_s
    )
    best = (score, beta.copy(), phase.copy(), None, parts)
    for gate in gates:
        for _ in range(2):
            terms = profile_phases(stats, beta, phase)
            proposed_beta, proposed_phase, info = joint_update(
                stats,
                terms.best,
                terms.aliases,
                beta,
                phase,
                sigma,
                bounds,
                terms.rms_hz < gate,
                drift_sigma_hz_s=drift_sigma_hz_s,
                drift_bound_hz_s=drift_bound_hz_s,
            )
            step = proposed_beta - beta
            step[:4] = (step[:4] + matching.PERIOD / 2) % matching.PERIOD - matching.PERIOD / 2
            accepted = None
            for fraction in (1.0, 0.5, 0.25, 0.125, 0.0625):
                b = beta + fraction * step
                b[:4] = (b[:4] + matching.PERIOD / 2) % matching.PERIOD - matching.PERIOD / 2
                p = phase + fraction * (proposed_phase - phase)
                value, _, detail = penalized_score(
                    stats, b, p, sigma, drift_sigma_hz_s=drift_sigma_hz_s
                )
                if value < score - 1e-6:
                    accepted = value, b, p, info, detail
                    break
            if accepted is None:
                break
            score, beta, phase, info, parts = accepted
            if score < best[0]:
                best = score, beta.copy(), phase.copy(), info, parts
    return best


def solve_joint(
    stats, initial, sigma, bounds, budget, *, drift_sigma_hz_s=2.0, drift_bound_hz_s=5.0
):
    initial = initial.copy()
    initial[4:8] = np.clip(initial[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
    phase_matrix, _ = proposal_phases(stats, initial, sigma, bounds, return_components=True)
    # Phase per component is allowed for proposal generation only. Final updates
    # always use one shared parameter per satellite across every component.
    phi = phase_matrix[stats["ci"]]
    seed_stats = dict(
        stats,
        mean=stats["mean"] - stats["hm"] * phi,
        xz=stats["xz"] - stats["xh"] * phi,
        rss=np.maximum(0, stats["rss"] - 2 * stats["zh"] * phi + stats["hh"] * phi**2),
    )
    shape = np.maximum(
        0, seed_stats["rss"] - seed_stats["xz"] ** 2 / np.maximum(stats["xx"][:, None], 1e-12)
    )
    seed_stats["shape_rms"] = np.sqrt(
        np.add.reduceat(shape, stats["starts"], axis=0) / stats["count"][:, None]
    )
    best = None
    count = 0
    for seed in matching.seed_calibrations(seed_stats, initial, budget):
        beta = seed.copy()
        beta[4:8] = np.clip(beta[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
        for g in range(4):
            if not np.any(stats["g"] == g):
                beta[g] = beta[g + 4] = 0
        phase = np.zeros(len(sigma)) if count == 0 else proposal_phases(stats, beta, sigma, bounds)
        result = improve(
            stats,
            beta,
            phase,
            sigma,
            bounds,
            drift_sigma_hz_s=drift_sigma_hz_s,
            drift_bound_hz_s=drift_bound_hz_s,
        )
        if best is None or result[0] < best[0]:
            best = result
        count += 1
    return (*best, count)


class Experiment:
    def __init__(
        self,
        recording,
        inputs,
        *,
        fitted_c,
        phase_enabled,
        drift_sigma_hz_s=2.0,
        drift_bound_hz_s=5.0,
    ):
        if not np.isfinite(drift_sigma_hz_s) or drift_sigma_hz_s <= 0:
            raise ValueError("finite positive drift prior sigma required")
        if not np.isfinite(drift_bound_hz_s) or drift_bound_hz_s < 0:
            raise ValueError("finite nonnegative drift bound required")
        self.drift_sigma_hz_s, self.drift_bound_hz_s = drift_sigma_hz_s, drift_bound_hz_s
        self.recording, self.inputs = recording, inputs
        self.receipt = json.loads((inputs / "receipt.json").read_text())
        if (
            hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest()
            != self.receipt["tracks_sha256"]
        ):
            raise ValueError("original Graph population changed")
        if (
            hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest()
            != self.receipt["bank_sha256"]
        ):
            raise ValueError("prepared causal phase bank changed")
        self.sky = dict(np.load(inputs / "bank.npz"))
        self.tracks = load_tracks(recording)
        self.groups = [(t["key"], [t]) for t in self.tracks if raw_curvature(t)]
        self.groups.sort(key=lambda row: row[0])
        self.curved_keys = frozenset(key for key, _ in self.groups)
        if not self.groups:
            raise ValueError("no individually measured-curved fragment supports a position fit")
        self.times = np.unique(
            np.concatenate([t["times"] for _, members in self.groups for t in members])
        )
        self.sigma = (
            self.sky["phase_sigma_s"] if phase_enabled else np.zeros(len(self.sky["norad"]))
        )
        self.bounds = self.sky["phase_bound_s"] if phase_enabled else np.zeros(len(self.sigma))
        self.initial = np.asarray(
            json.loads((recording / "merged.json").read_text())["calibration"]["beta"]
        )
        self.initial[4:8] = np.clip(
            self.initial[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s
        )
        if fitted_c:
            self.initial = np.r_[self.initial, 0.0]
        self.fitted_c, self.phase_enabled = fitted_c, phase_enabled
        self.geometry = prepare_phase_geometry(self.sky, self.times)
        inertial_velocity = self.sky["velocity_km_s"].copy()
        inertial_velocity[:, :, 0] -= 7.29211514670698e-5 * self.sky["position_km"][:, :, 1]
        inertial_velocity[:, :, 1] += 7.29211514670698e-5 * self.sky["position_km"][:, :, 0]
        speed = np.max(np.linalg.norm(inertial_velocity, axis=2), axis=1)
        self.phase_radius_km = self.bounds * (speed + 0.02) + 0.01 * self.bounds**2

    def set_observation_partition(self, curve_tracks, background_observation_ids):
        """Bind a lossless radio-only partition before calibration or search.

        The caller supplies unsmoothed original values and explicit background
        IDs. Only the measured-curved cores can calibrate. Association remains
        a curve-only result; the returned receipt supplies its full denominator.
        """
        originals = {}
        for track in self.tracks:
            for i, oid in enumerate(track["observation_ids"]):
                if oid in originals:
                    raise ValueError("duplicate original observation identity")
                originals[oid] = track, i
        background = list(background_observation_ids)
        retained = []
        if len({t["key"] for t in curve_tracks}) != len(curve_tracks):
            raise ValueError("duplicate core track key")
        for track in curve_tracks:
            if (
                not len(track["times"])
                or len(track["times"]) != len(track["values"])
                or len(track["times"]) != len(track["observation_ids"])
            ):
                raise ValueError("nonempty matching core measurement arrays required")
            for i, oid in enumerate(track["observation_ids"]):
                if oid not in originals:
                    raise ValueError("unknown partition observation")
                parent, j = originals[oid]
                if (
                    track["key"] != parent["key"]
                    or track["receiver"] != parent["receiver"]
                    or track["channel"] != parent["channel"]
                    or track["rf_hz"] != parent["rf_hz"]
                    or track["times"][i] != parent["times"][j]
                    or track["values"][i] != parent["values"][j]
                ):
                    raise ValueError("partition changed original measurement binding")
                retained.append(oid)
        if len(set(retained)) != len(retained) or len(set(background)) != len(background):
            raise ValueError("duplicate partition observation")
        if set(retained) & set(background) or set(retained) | set(background) != set(originals):
            raise ValueError("curve/background partition must preserve every original observation")
        groups = [(t["key"], [t]) for t in curve_tracks if raw_curvature(t)]
        groups.sort(key=lambda row: row[0])
        if not groups:
            raise ValueError("no measured-curved core supports calibration")
        times = np.unique(np.concatenate([t["times"] for _, members in groups for t in members]))
        geometry = prepare_phase_geometry(self.sky, times)
        self.tracks, self.groups = curve_tracks, groups
        self.curved_keys = frozenset(key for key, _ in groups)
        self.times, self.geometry = times, geometry
        self.background_observation_ids = frozenset(background)
        return dict(
            original_points=len(originals),
            curve_points=len(retained),
            background_points=len(background),
            calibration_fragments=len(groups),
            calibration_points=sum(len(t["times"]) for _, members in groups for t in members),
            points_dropped=0,
        )

    def statistics(self, frequency, elevation, derivative, *, anchor=None, visibility_margin=None):
        base = matching.statistics(
            self.groups,
            dict(time_s=self.times, doppler_0=frequency, elevation_deg=elevation),
            {str(t["channel"]): 0.0 for t in self.tracks},
        )
        stats = augment_phase_statistics(base, self.times, frequency, derivative)
        if visibility_margin is not None:
            for fi, track in enumerate(stats["fragments"]):
                indexes = np.searchsorted(self.times, track["times"])
                stats["visible"][fi] = (
                    np.min(elevation[:, indexes] + visibility_margin[:, indexes], axis=1) >= 0
                )
            stats["component_visible"] = np.logical_and.reduceat(
                stats["visible"], stats["starts"], axis=0
            )
        return stats if anchor is None else recenter_phases(stats, anchor)

    def fit(self, latitude, longitude, budget, *, exact=False):
        frequency, elevation, derivative = phase_linear_frequency(
            self.geometry, latitude, longitude
        )
        observer = geodetic_to_ecef_km(latitude, longitude, 0.0)
        base = self.geometry.geometry
        distance = np.sqrt(
            base.position_norm_squared
            - 2 * np.einsum("snj,j->sn", base.position_km, observer)
            + observer @ observer
        )
        margin = np.rad2deg(np.arcsin(np.minimum(1.0, self.phase_radius_km[:, None] / distance)))
        stats = self.statistics(frequency, elevation, derivative, visibility_margin=margin)
        score, beta, phase, info, parts, seeds = solve_joint(
            stats,
            self.initial,
            self.sigma,
            self.bounds,
            budget,
            drift_sigma_hz_s=self.drift_sigma_hz_s,
            drift_bound_hz_s=self.drift_bound_hz_s,
        )
        exact_history = []
        if exact and self.phase_enabled:
            best_exact = None
            for iteration in range(5):
                geometry = prepare_phase_geometry(self.sky, self.times, phase)
                f, e, h = phase_linear_frequency(geometry, latitude, longitude)
                local = self.statistics(f, e, h, anchor=phase)
                value, terms, detail = penalized_score(
                    local, beta, phase, self.sigma, drift_sigma_hz_s=self.drift_sigma_hz_s
                )
                exact_history.append(dict(iteration=iteration, score=value))
                if best_exact is None or value < best_exact[0]:
                    best_exact = value, beta.copy(), phase.copy(), info, detail
                result = improve(
                    local,
                    beta,
                    phase,
                    self.sigma,
                    self.bounds,
                    gates=(1000.0, 450.0),
                    drift_sigma_hz_s=self.drift_sigma_hz_s,
                    drift_bound_hz_s=self.drift_bound_hz_s,
                )
                if (
                    np.max(np.abs(result[2] - phase)) < 1e-4
                    and np.max(np.abs(result[1] - beta)) < 0.05
                ):
                    break
                _, beta, phase, info, _ = result
            score, beta, phase, info, parts = best_exact
        return dict(
            latitude_deg=latitude,
            longitude_deg=longitude,
            score=float(score),
            beta=beta.tolist(),
            phases_s=phase.tolist(),
            phase_norads=self.sky["norad"].tolist(),
            fitted_c=self.fitted_c,
            phase_enabled=self.phase_enabled,
            seed_states=seeds,
            score_parts=parts,
            calibration=clean_info(info),
            nonlinear_history=exact_history,
            exact_phase_geometry=bool(exact or not self.phase_enabled),
            drift_sigma_hz_s=self.drift_sigma_hz_s,
            drift_bound_hz_s=self.drift_bound_hz_s,
        )

    def associate(self, fit):
        times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        phases = np.asarray(fit["phases_s"])
        frequency, elevation = phase_frequency_grid(
            self.sky, times, fit["latitude_deg"], fit["longitude_deg"], phase_seconds=phases
        )
        groups = [(t["key"], [t]) for t in self.tracks]
        stats = matching.statistics(
            groups,
            dict(time_s=times, doppler_0=frequency, elevation_deg=elevation),
            {str(t["channel"]): 0.0 for t in self.tracks},
        )
        beta = np.asarray(fit["beta"])
        terms = profile_component_bias(stats, beta, bias_sigma_hz=1000)
        rows = []
        for fi, track in enumerate(self.tracks):
            j = terms.best[fi]
            g = matching.group(track)
            cal = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
            if len(beta) == 9:
                cal += beta[8] * (track["rf_hz"] / 1e9 - 11.5)
            residual = track["values"] + terms.aliases[fi, j] * matching.PERIOD - cal
            residual -= (
                track["rf_hz"] / 11.5e9 * frequency[j, np.searchsorted(times, track["times"])]
            )
            residual -= terms.bias_hz[fi, j]
            diagnostic = matching.noise_screen(residual, track["times"])
            compatible = bool(
                stats["component_visible"][fi, j]
                and terms.rms_hz[fi] <= 450
                and abs(terms.bias_hz[fi, j]) <= 3000
                and diagnostic["noise_screen_pass"]
            )
            rows.append(
                dict(
                    component=track["key"],
                    candidate_norad=int(self.sky["norad"][j]),
                    phase_s=float(phases[j]),
                    points=len(track["times"]),
                    rms_hz=float(terms.rms_hz[fi]),
                    bias_hz=float(terms.bias_hz[fi, j]),
                    compatible=compatible,
                    active_curvature=track["key"] in self.curved_keys,
                    residual_diagnostics=diagnostic,
                )
            )
        group_support = np.zeros(4, int)
        satellite_support = {}
        for track, row in zip(self.tracks, rows, strict=True):
            if row["compatible"] and row["active_curvature"]:
                group_support[matching.group(track)] += 1
                satellite_support[row["candidate_norad"]] = (
                    satellite_support.get(row["candidate_norad"], 0) + 1
                )
        for track, row in zip(self.tracks, rows, strict=True):
            row["frequency_compatible_before_calibration_support"] = row["compatible"]
            row["qualified_curved_hardware_support"] = int(group_support[matching.group(track)])
            row["qualified_curved_satellite_support"] = satellite_support.get(
                row["candidate_norad"], 0
            )
            row["compatible"] &= row["qualified_curved_hardware_support"] > 0
            if self.phase_enabled and abs(row["phase_s"]) > 1e-3:
                row["compatible"] &= row["qualified_curved_satellite_support"] > 0
        return dict(
            points=sum(len(t["times"]) for t in self.tracks),
            fragments=len(self.tracks),
            compatible_points=sum(r["points"] for r in rows if r["compatible"]),
            compatible_fragments=sum(r["compatible"] for r in rows),
            rows=rows,
            independent_identity_truth=False,
        )


def protocol(experiment, output, action, budget):
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__),
        Path(matching.__file__),
        Path(__file__).with_name("search_merged_track_position.py"),
        root / "src/leo/analysis/research/shared_orbit_phase_fit.py",
        root / "src/leo/analysis/research/phase_linear_geometry.py",
        root / "src/leo/analysis/research/orbit_phase_geometry.py",
    ]
    write(
        output / "protocol.json",
        dict(
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            action=action,
            phase_enabled=experiment.phase_enabled,
            fitted_c=experiment.fitted_c,
            bank_receipt=experiment.receipt,
            calibration_mode="individually curved original fragments only",
            all_original_points_in_association=True,
            graph_points=sum(len(t["times"]) for t in experiment.tracks),
            calibration_points=sum(
                len(t["times"]) for _, members in experiment.groups for t in members
            ),
            calibration_fragments=len(experiment.groups),
            final_generated_seed_budget=budget,
            discovery_generated_seed_budget=4,
            evaluation_position_used_in_search=False,
            phase_prior_is_calibrated_covariance=False,
            observations_withheld=0,
            hardware_groups=["RX1 low", "RX1 high", "RX2 low", "RX2 high"],
            calibration_pivot_s=150.0,
            independent_hardware_per_scan=True,
            drift_sigma_hz_s=experiment.drift_sigma_hz_s,
            drift_bound_hz_s=experiment.drift_bound_hz_s,
        ),
    )


def search(experiment, output, budget):
    center_lat, center_lon = experiment.receipt["regional_center"]
    scale = 111.32 * np.cos(np.deg2rad(center_lat))
    progress, fits = [], {}

    def evaluate(point, final=False):
        started = time.monotonic()
        lat, lon = center_lat + point[1] / 111, center_lon + point[0] / scale
        fit = experiment.fit(lat, lon, budget if final else 4, exact=final)
        key = tuple(np.round(point, 9))
        fits[key] = fit
        progress.append(
            dict(
                east_north_km=list(point),
                score=fit["score"],
                final=final,
                elapsed_seconds=time.monotonic() - started,
            )
        )
        write(output / "progress.json", progress)
        if len(progress) % 20 == 0:
            print(
                json.dumps(dict(evaluations=len(progress), best=min(r["score"] for r in progress))),
                flush=True,
            )
        return fit["score"]

    result = regional_search(evaluate, radius=experiment.receipt["radius_km"])
    finalists = []
    for row in result["basins"] + sorted(result["trace"], key=lambda r: r["score"]):
        point = np.asarray(row["east_north_km"])
        if all(np.linalg.norm(point - r["east_north_km"]) >= 0.2 for r in finalists):
            finalists.append(dict(east_north_km=point.tolist(), score=evaluate(point, final=True)))
        if len(finalists) == 8:
            break
    winner = min(finalists, key=lambda r: r["score"])
    fit = fits[tuple(np.round(winner["east_north_km"], 9))]
    result.update(
        endpoint=fit,
        finalists=finalists,
        score=winner["score"],
        east_north_km=winner["east_north_km"],
        source_id=experiment.receipt["source_id"],
        global_optimum_proven=False,
        goal_complete=False,
    )
    write(output / "fit.json", result)
    write(output / "association.json", experiment.associate(fit))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("search", "diagnose"))
    p.add_argument("--recording", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", action="store_true")
    p.add_argument("--fitted-c", action="store_true")
    p.add_argument("--seed-budget", type=int, default=32)
    p.add_argument("--drift-sigma-hz-s", type=float, default=2.0)
    p.add_argument("--drift-bound-hz-s", type=float, default=5.0)
    p.add_argument("--previous-fit", type=Path)
    p.add_argument("--reference-latitude", type=float, required=True)
    p.add_argument("--reference-longitude", type=float, required=True)
    a = p.parse_args()
    if a.seed_budget < 1:
        p.error("positive seed budget required")
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    experiment = Experiment(
        a.recording,
        a.inputs,
        fitted_c=a.fitted_c,
        phase_enabled=a.phase,
        drift_sigma_hz_s=a.drift_sigma_hz_s,
        drift_bound_hz_s=a.drift_bound_hz_s,
    )
    protocol(experiment, a.output, a.action, a.seed_budget)
    if a.action == "search":
        result = search(experiment, a.output, a.seed_budget)
        fit = result["endpoint"]
        error = distance_km(
            (fit["latitude_deg"], fit["longitude_deg"]),
            (a.reference_latitude, a.reference_longitude),
        )
        write(
            a.output / "evaluation.json",
            dict(
                position_error_km=error,
                within_0_5km=error < 0.5,
                reference_used_only_after_fit=True,
                fit_sha256=hashlib.sha256((a.output / "fit.json").read_bytes()).hexdigest(),
                goal_complete=False,
            ),
        )
        print(json.dumps(dict(position_error_km=error)), flush=True)
    else:
        if a.previous_fit is None:
            p.error("diagnostic requires a previously sealed blind fit")
        previous = json.loads(a.previous_fit.read_text())["endpoint"]
        sites = [
            ("supplied_evaluation_site", a.reference_latitude, a.reference_longitude),
            ("previous_blind_endpoint", previous["latitude_deg"], previous["longitude_deg"]),
        ]
        rows = []
        for label, lat, lon in sites:
            fit = experiment.fit(lat, lon, a.seed_budget, exact=True)
            row = dict(
                site=label,
                fit=fit,
                association=experiment.associate(fit),
                use="diagnostic only; not a geographic initializer",
            )
            rows.append(row)
            write(a.output / "diagnosis.json", rows)
            print(
                json.dumps(
                    dict(
                        site=label,
                        score=fit["score"],
                        compatible_points=row["association"]["compatible_points"],
                    )
                ),
                flush=True,
            )
