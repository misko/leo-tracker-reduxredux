"""Two bounded association prototypes on the unchanged S01 graph partition."""

import hashlib
import itertools
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import write
from fit_s01_69333_tle_parameter import common_epoch_elements, perturb
from inventory_clipped_phase_cohort import ROOT, load_study
from sgp4.api import Satrec

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.shared_satellite_correction import (
    NOISE_HZ,
    profile_curve,
    ridge_shared_fit,
    soft_curve_responsibilities,
)
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from leo.sky.propagation import ElementSetCatalogue

OUTPUT = ROOT / "reports/2026_10_17_s01_shared_satellite_prototypes"
BASELINE = ROOT / "reports/2026_10_17_s01_phase_sensitivity"
TLES = ROOT / "reports/2026_10_17_s01_ch4_t001_diagnosis/bracketing_tles.json"
RAW = ROOT / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"


def make_priors():
    exported = json.loads((OUTPUT / "causal_prior_inputs.json").read_text())
    tles = json.loads(TLES.read_text())
    priors = {}
    for number, rows in exported["candidates"].items():
        base = Satrec.twoline2rv(*tles["past"][number]["lines"])
        epoch = int(round(((base.jdsatepoch - 2440587.5) + base.jdsatepochF) * 86400e9))
        vectors = []
        for row in rows:
            assert row["element_epoch_utc_ns"] <= exported["cutoff_utc_ns"]
            assert row["collected_utc_ns"] <= exported["cutoff_utc_ns"]
            mean = common_epoch_elements(Satrec.twoline2rv(*row["lines"]), epoch)
            vectors.append([mean["e_cos_omega"], mean["e_sin_omega"]])
        differences = np.diff(vectors, axis=0)
        covariance = (
            differences.T @ differences / len(differences) if len(differences) else np.eye(2) * 1e-8
        )
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        covariance = (
            eigenvectors * np.clip(eigenvalues, (2e-5) ** 2, (3e-4) ** 2)
        ) @ eigenvectors.T
        priors[int(number)] = dict(
            covariance=covariance,
            past_epochs=len(rows),
            difference_count=len(differences),
            differences=differences,
        )
    write(OUTPUT / "orbital_priors.json", priors)
    return priors, tles


class Prototype:
    def __init__(self, method, fitted_c, priors, tles):
        self.method, self.arm = method, "fitted_c" if fitted_c else "c0"
        self.study, *_ = load_study("DSX01-S01", fitted_c)
        self.tracks = self.study.tracks
        self.fit = json.loads((BASELINE / self.arm / "fit_cap_2.7.json").read_text())
        self.old = json.loads((BASELINE / self.arm / "association_cap_2.7.json").read_text())
        self.oldrows = self.old["association"]["rows"]
        assert [t["key"] for t in self.tracks] == [r["component"] for r in self.oldrows]
        self.beta = np.array(self.fit["beta"])
        self.norads = self.study.sky["norad"]
        self.lookup = {int(n): j for j, n in enumerate(self.norads)}
        self.times = np.unique(np.concatenate([t["times"] for t in self.tracks]))
        self.index = [np.searchsorted(self.times, t["times"]) for t in self.tracks]
        self.curved = np.array([t["key"] in self.study.curved_keys for t in self.tracks])
        self.seed = {
            i: r["candidate_norad"]
            for i, r in enumerate(self.oldrows)
            if r["compatible"] and self.curved[i]
        }
        self.initial_nom = np.array([r["candidate_norad"] for r in self.oldrows])
        self.priors, self.tles = priors, tles
        self.origin = tles["anchor_utc_ns"]
        self.satellites = {n: Satrec.twoline2rv(*tles["past"][str(n)]["lines"]) for n in priors}
        self.theta, self.tref, self.covariance = {}, {}, {}
        self.y = []
        for t in self.tracks:
            g = matching.group(t)
            hw = self.beta[g] + self.beta[g + 4] * (t["times"] - 150) / 150
            if len(self.beta) == 9:
                hw += self.beta[8] * (t["rf_hz"] / 1e9 - 11.5)
            self.y.append(t["values"] - hw)
        for n in priors:
            j = self.lookup[n]
            own = [
                i for i in range(len(self.tracks)) if self.curved[i] and self.initial_nom[i] == n
            ]
            self.tref[n] = float(np.median(np.concatenate([self.tracks[i]["times"] for i in own])))
            if method == "family_extension":
                self.theta[n] = np.array([self.fit["phases_s"][j], 0.0])
                self.covariance[n] = np.eye(2) * 1e12
            else:
                self.theta[n] = np.array([self.fit["phases_s"][j], 0.0, 0.0])
                cov = np.zeros((3, 3))
                cov[0, 0] = max(1.0, float(self.study.sigma[j])) ** 2
                cov[1:, 1:] = priors[n]["covariance"]
                self.covariance[n] = cov
        self.initial_theta = {n: t.copy() for n, t in self.theta.items()}
        self.calibration_members = {}
        self.base_f = np.empty((len(self.norads), len(self.times)))
        self.base_e = np.empty_like(self.base_f)
        for begin in range(0, len(self.norads), 96):
            sel = slice(begin, begin + 96)
            sky = {k: self.study.sky[k][sel] for k in ("position_km", "velocity_km_s")}
            sky["time_s"] = self.study.sky["time_s"]
            geom = prepare_phase_geometry(sky, self.times, np.array(self.fit["phases_s"])[sel])
            f, e, _ = phase_linear_frequency(geom, matching.LATITUDE, matching.LONGITUDE)
            self.base_f[sel], self.base_e[sel] = f, e

    def forward(self, n, theta, times):
        sat = self.satellites[n]
        if self.method != "family_extension":
            sat = perturb(perturb(sat, "e_cos_omega", theta[1]), "e_sin_omega", theta[2])
        cat = ElementSetCatalogue((str(n),), (n,), (sat,))
        p, v, usable = matching.ecef_states(cat, self.origin, times + theta[0])
        assert usable.all()
        angle = EARTH_ROTATION_RAD_S * theta[0]
        for array in (p, v):
            x, y = array[..., 0].copy(), array[..., 1].copy()
            array[..., 0] = np.cos(angle) * x - np.sin(angle) * y
            array[..., 1] = np.sin(angle) * x + np.cos(angle) * y
        observer = geodetic_to_ecef_km(matching.LATITUDE, matching.LONGITUDE, 0)
        _, elevation, _, rate = look_angles(
            p, v, observer, ecef_to_enu_matrix(matching.LATITUDE, matching.LONGITUDE)
        )
        frequency = -11.5e9 / 299792.458 * rate[0]
        if self.method == "family_extension":
            frequency += theta[1] * (times - self.tref[n])
        return frequency, elevation[0]

    def nearby(self, i, anchors):
        t = self.tracks[i]["times"]
        return any(
            max(0, min(t) - max(self.tracks[k]["times"]), min(self.tracks[k]["times"]) - max(t))
            <= 30
            for k in anchors
        )

    def expectation(self):
        f, e = self.base_f.copy(), self.base_e.copy()
        changed = set()
        for n, theta in self.theta.items():
            if not np.array_equal(theta, self.initial_theta[n]):
                j = self.lookup[n]
                f[j], e[j] = self.forward(n, theta, self.times)
                changed.add(n)
        shape = (len(self.tracks), len(self.norads))
        scores, feasible, gamma = np.empty(shape), np.zeros(shape, bool), np.zeros(shape)
        for i, t in enumerate(self.tracks):
            terms = profile_curve(self.y[i], t["rf_hz"] / 11.5e9 * f[:, self.index[i]])
            visible = np.min(e[:, self.index[i]], axis=1) >= 0
            scores[i] = terms["score"]
            possible = visible & (terms["rms"] <= 450) & (abs(terms["bias"]) <= 3000)
            if self.method == "family_extension":
                for n in changed:
                    if not self.nearby(i, self.calibration_members.get(n, [])):
                        possible[self.lookup[n]] = False
            candidates = np.flatnonzero(possible)
            if len(candidates):
                noise = batch_noise_screen(terms["residual"][candidates], t["times"])
                feasible[i, candidates] = noise["noise_screen_pass"]
            if self.curved[i]:
                gamma[i], _ = soft_curve_responsibilities(
                    terms["score"], terms["rms"], terms["bias"], visible, len(t["times"])
                )
        choice = np.argmin(np.where(feasible, scores, np.inf), axis=1)
        if self.method == "family_extension":
            for i, n in self.seed.items():
                choice[i] = self.lookup[n]
        admitted = feasible[np.arange(len(choice)), choice]
        # An extra satellite correction requires two channels with assigned
        # measured curvature. No linear track supplies this ownership.
        for n in changed:
            j = self.lookup[n]
            owners = [
                i for i in range(len(choice)) if self.curved[i] and admitted[i] and choice[i] == j
            ]
            if len({self.tracks[i]["channel"] for i in owners}) < 2:
                feasible[:, j] = False
        choice = np.argmin(np.where(feasible, scores, np.inf), axis=1)
        if self.method == "family_extension":
            for i, n in self.seed.items():
                choice[i] = self.lookup[n]
        admitted = feasible[np.arange(len(choice)), choice]
        curved_owner = {
            int(self.norads[j]) for i, j in enumerate(choice) if self.curved[i] and admitted[i]
        }
        # A linear curve needs an owner only for a learned satellite phase or
        # extra correction. An unshifted, unadjusted TLE requires no satellite
        # calibration, matching the established association policy.
        requires_owner = np.abs(np.array(self.fit["phases_s"])) > 1e-3
        for n in changed:
            requires_owner[self.lookup[n]] = True
        for i in np.flatnonzero(~self.curved):
            for j in np.flatnonzero(requires_owner):
                if int(self.norads[j]) not in curved_owner:
                    feasible[i, j] = False
            choice[i] = np.argmin(np.where(feasible[i], scores[i], np.inf))
            admitted[i] = feasible[i, choice[i]]
        outrows = []
        for i, t in enumerate(self.tracks):
            j = int(choice[i])
            if not admitted[i]:
                j = int(np.argmin(scores[i]))
            n = int(self.norads[j])
            terms = profile_curve(self.y[i], t["rf_hz"] / 11.5e9 * f[j, self.index[i]])
            noise = matching.noise_screen(terms["residual"][0], t["times"])
            outrows.append(
                dict(
                    component=t["key"],
                    candidate_norad=n,
                    points=len(t["times"]),
                    active_curvature=bool(self.curved[i]),
                    compatible=bool(admitted[i]),
                    rms_hz=float(terms["rms"][0]),
                    bias_hz=float(terms["bias"][0]),
                    residual_hz=terms["residual"][0],
                    times_s=t["times"],
                    diagnostics=noise,
                    feasible_candidates=int(feasible[i].sum()),
                )
            )
        return dict(rows=outrows, gamma=gamma, scores=scores)

    def score_state(self, n, theta, pool, weights):
        times = np.unique(np.concatenate([self.tracks[i]["times"] for i in pool]))
        f, e = self.forward(n, theta, times)
        score, supporting = 0.0, []
        preserved = {i for i, owner in self.seed.items() if owner == n}
        for i, weight in zip(pool, weights, strict=True):
            t = self.tracks[i]
            ix = np.searchsorted(times, t["times"])
            terms = profile_curve(self.y[i], t["rf_hz"] / 11.5e9 * f[ix])
            noise = matching.noise_screen(terms["residual"][0], t["times"])
            ok = bool(
                np.min(e[ix]) >= 0
                and terms["rms"][0] <= 450
                and abs(terms["bias"][0]) <= 3000
                and noise["noise_screen_pass"]
            )
            if self.method == "family_extension" and i in preserved and not ok:
                return np.inf, []
            cost = min(float(terms["score"][0]) / NOISE_HZ**2, 36) if ok else 36
            score += weight * min(len(t["times"]), 50) * cost
            if ok:
                supporting.append(i)
        extra = np.linalg.norm(theta[1:]) > 1e-10
        if extra and len({self.tracks[i]["channel"] for i in supporting}) < 2:
            return np.inf, []
        score += (len(theta) if extra else 1) * np.log(max(2, len(times)))
        if self.method != "family_extension":
            score += float(theta @ np.linalg.solve(self.covariance[n], theta))
        return score, supporting

    def clip(self, n, theta):
        theta = theta.copy()
        theta[0] = np.clip(theta[0], -15, 15)
        if self.method == "family_extension":
            theta[1] = np.clip(theta[1], -20, 20)
        else:
            theta[1:] = np.clip(theta[1:], -0.0008, 0.0008)
            mahalanobis = np.sqrt(
                theta[1:] @ np.linalg.solve(self.covariance[n][1:, 1:], theta[1:])
            )
            if mahalanobis > 5:
                theta[1:] *= 5 / mahalanobis
        return theta

    def tangent_fit(self, n, start, members, weights):
        times = np.unique(np.concatenate([self.tracks[i]["times"] for i in members]))
        f, _ = self.forward(n, start, times)
        derivatives = []
        for k, epsilon in enumerate([0.05, 0.01] if len(start) == 2 else [0.05, 2e-5, 2e-5]):
            if self.method == "family_extension" and k == 1:
                derivatives.append(times - self.tref[n])
                continue
            plus, minus = start.copy(), start.copy()
            plus[k] += epsilon
            minus[k] -= epsilon
            derivatives.append(
                (self.forward(n, plus, times)[0] - self.forward(n, minus, times)[0]) / (2 * epsilon)
            )
        features, values = [], []
        for i in members:
            t = self.tracks[i]
            ix, q = np.searchsorted(times, t["times"]), t["rf_hz"] / 11.5e9
            x = q * np.array(derivatives)[:, ix].T
            raw = self.y[i] - q * f[ix]
            raw += round(-float(np.mean(raw)) / matching.PERIOD) * matching.PERIOD
            features.append(x)
            values.append(raw + x @ start)
        proposal, _, _ = ridge_shared_fit(
            features, values, weights, self.covariance[n], [self.curved[i] for i in members]
        )
        return self.clip(n, proposal)

    def maximize(self, state):
        changes = []
        for n, current in list(self.theta.items()):
            j = self.lookup[n]
            own_seeds = [i for i, owner in self.seed.items() if owner == n]
            if self.method == "family_extension":
                if not own_seeds:
                    continue
                pool = [
                    i
                    for i in range(len(self.tracks))
                    if self.curved[i]
                    and (i not in self.seed or self.seed[i] == n)
                    and (
                        self.initial_nom[i] == n
                        or state["rows"][i]["candidate_norad"] == n
                        or state["gamma"][i, j] > 0.05
                    )
                    and self.nearby(i, own_seeds)
                ]
                weights = np.ones(len(pool))
            else:
                pool = [
                    i
                    for i in range(len(self.tracks))
                    if self.curved[i] and state["gamma"][i, j] > 0.05
                ]
                weights = state["gamma"][pool, j]
            if len({self.tracks[i]["channel"] for i in pool}) < 2:
                continue
            best, support = self.score_state(n, current, pool, weights)
            winner = current.copy()
            subsets = [list(range(len(pool)))]
            if self.method == "family_extension":
                subsets += [
                    list(pair)
                    for pair in itertools.combinations(range(len(pool)), 2)
                    if self.tracks[pool[pair[0]]]["channel"]
                    != self.tracks[pool[pair[1]]]["channel"]
                ]
            for subset in subsets:
                theta = current.copy()
                for _ in range(2):
                    proposal = self.tangent_fit(
                        n, theta, [pool[k] for k in subset], weights[subset]
                    )
                    theta = proposal
                for fraction in (1.0, 0.5, 0.25):
                    proposal = current + fraction * (theta - current)
                    score, supported = self.score_state(n, proposal, pool, weights)
                    if score < best - 1e-8:
                        best, winner, support = score, proposal, supported
            if not np.array_equal(winner, current):
                self.theta[n] = winner
                self.calibration_members[n] = support
                changes.append(
                    dict(
                        norad=n,
                        old=current,
                        new=winner,
                        score=best,
                        pool=[self.tracks[i]["key"] for i in pool],
                        supporting_curved=[self.tracks[i]["key"] for i in support],
                    )
                )
        return changes

    def save(self, state, folder, history):
        raw = [
            r
            for line in RAW.read_text().splitlines()
            if (r := json.loads(line))["source_id"] == "S01"
        ]
        raw_ids = {r["observation_id"] for r in raw}
        ids = {
            oid
            for t, r in zip(self.tracks, state["rows"], strict=True)
            if r["compatible"]
            for oid in t["observation_ids"]
        }
        assert len(raw_ids) == 4797 and ids <= raw_ids
        oldids = set(self.old["associated_observation_ids"])
        relabeled = [
            r["component"]
            for r, old in zip(state["rows"], self.oldrows, strict=True)
            if r["compatible"]
            and old["compatible"]
            and r["candidate_norad"] != old["candidate_norad"]
        ]
        matched = [r for r in state["rows"] if r["compatible"]]
        summary = dict(
            method=self.method,
            arm=self.arm,
            associated=len(ids),
            raw_points=4797,
            percent_associated=100 * len(ids) / 4797,
            unassociated=4797 - len(ids),
            polynomial_fragments=len(matched),
            mean_points_per_fragment=len(ids) / len(matched),
            candidate_satellites=len({r["candidate_norad"] for r in matched}),
            gained=len(ids - oldids),
            lost=len(oldids - ids),
            relabeled=relabeled,
            iterations=len(history) - 1,
            model_does_not_merge_fragments=True,
        )
        write(folder / "summary.json", summary)
        write(
            folder / "association.json",
            dict(
                rows=state["rows"],
                summary=summary,
                associated_observation_ids=sorted(ids),
                unassociated_observation_ids=sorted(raw_ids - ids),
            ),
        )
        write(
            folder / "parameters.json",
            {
                n: dict(
                    theta=t,
                    reference_time_s=self.tref[n],
                    initial_theta=self.initial_theta[n],
                    covariance=self.covariance[n],
                    calibration_members=[
                        self.tracks[i]["key"] for i in self.calibration_members.get(n, [])
                    ],
                )
                for n, t in self.theta.items()
            },
        )
        write(folder / "history.json", history)
        return summary


def run():
    priors, tles = make_priors()
    summaries = []
    for method in ("family_extension", "prior_orbit_em"):
        for fitted_c in (False, True):
            experiment = Prototype(method, fitted_c, priors, tles)
            folder = OUTPUT / method / experiment.arm
            folder.mkdir(parents=True, exist_ok=True)
            state = experiment.expectation()
            history = [
                dict(
                    iteration=0,
                    points=sum(r["points"] for r in state["rows"] if r["compatible"]),
                    changes=[],
                )
            ]
            for iteration in range(1, 4):
                changes = experiment.maximize(state)
                state = experiment.expectation()
                history.append(
                    dict(
                        iteration=iteration,
                        points=sum(r["points"] for r in state["rows"] if r["compatible"]),
                        changes=changes,
                    )
                )
                print(
                    json.dumps(
                        dict(
                            method=method,
                            arm=experiment.arm,
                            iteration=iteration,
                            points=history[-1]["points"],
                            satellites_updated=len(changes),
                        )
                    ),
                    flush=True,
                )
                write(folder / "history.json", history)
                if not changes:
                    break
            summaries.append(experiment.save(state, folder, history))
            write(OUTPUT / "summary.json", summaries)
    write(
        OUTPUT / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            supplied_gps_fixed=True,
            no_geographic_accuracy_experiment=True,
            causal_tle_only=True,
            no_future_elements_used_for_fit_or_priors=True,
            graph_partition_and_original_raw_population_fixed=True,
            original_raw_glrt=4797,
            graph_polynomial_points=4486,
            no_linear_calibration_or_linear_proposal_ranking=True,
            c0_and_fitted_c_match_observations_candidate_set_priors_bounds_iterations=True,
            candidate_count=1707,
            maximum_iterations=3,
            family_extension=dict(
                phase_box_s=15,
                rate_box_hz_s=20,
                minimum_support_channels=2,
                gap_s=30,
                old_curved_labels_preserved=True,
                rate_is_empirical_not_declared_lnb_drift=True,
            ),
            prior_orbit_em=dict(
                phase_sigma_floor_s=1,
                phase_box_s=15,
                eccentricity_sigma_floor=2e-5,
                eccentricity_sigma_cap=3e-4,
                absolute_e_box=0.0008,
                maximum_prior_radius=5,
                minimum_support_channels=2,
                curve_responsibilities_are_experimental_not_identity_probabilities=True,
                generalized_em_proposals_with_hard_final_gates=True,
            ),
            per_curve_gate=dict(
                rms_hz=450,
                bias_hz=3000,
                mean_z=3,
                slope_z=3,
                quadratic_bic_gain=10,
                maximum_step_z=4,
                lag1="4/sqrt(N)",
            ),
            no_claim_pooled_residual_independence_or_authenticated_ids=True,
        ),
    )


if __name__ == "__main__":
    run()
