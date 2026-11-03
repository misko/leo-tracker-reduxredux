"""Correlate component-bias priors only when independent frame timing links them."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_causal_clock import lock_aliases
from prototype_s01_receiver_drift import ReceiverDriftProblem

from leo.analysis.research.orbit_uncertainty import low_rank_marginal
from leo.analysis.research.retained_track_likelihood import PERIOD


def linked_tracks(scan, seed):
    data = json.loads((OUTPUT / "frame_coherent_calibration.json").read_text())[scan.case]
    index = {oid: i for i in scan.curved for oid in scan.tracks[i]["observation_ids"]}
    labels = {r["component"]: r["candidate_index"] for r in seed["rows"] if r["active_curvature"]}
    edges = Counter()
    for pair in data["pairs"]:
        if pair["frame_coherent"] and pair["both_original_curved"]:
            a, b = [index[oid] for oid in pair["observation_ids"]]
            edges[tuple(sorted((a, b)))] += 1
    parents = {i: i for i in scan.curved}
    skipped = []
    accepted = []

    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i

    for (a, b), count in edges.items():
        if count < 3:
            continue
        if labels[scan.tracks[a]["key"]] != labels[scan.tracks[b]["key"]]:
            skipped.append(
                dict(left=scan.tracks[a]["key"], right=scan.tracks[b]["key"], pairs=count)
            )
            continue
        parents[root(a)] = root(b)
        accepted.append(dict(left=scan.tracks[a]["key"], right=scan.tracks[b]["key"], pairs=count))
    groups = defaultdict(list)
    for i in scan.curved:
        groups[root(i)].append(i)
    return [g for g in groups.values() if len(g) > 1], dict(
        accepted_edges=accepted, skipped_conflicting_candidate_edges=skipped
    )


class FrameBiasFamilies(AnchoredFamilies):
    def __init__(self, *args, independent_sigma=100.0, provided_links=None):
        self.ready = False
        super().__init__(*args)
        if self.method == "penalized_split":
            raise ValueError("split covariance not implemented in this prototype")
        if not 0 < independent_sigma <= 1000:
            raise ValueError("independent bias scale must be in (0,1000]")
        self.independent_sigma = independent_sigma
        links, self.link_metadata = (
            linked_tracks(self.scan, args[1]) if provided_links is None else (provided_links, {})
        )
        self.linked_group = {i: k for k, group in enumerate(links) for i in group}
        self.member_bias_sigmas = {
            i: (independent_sigma if i in self.linked_group else 1000.0) for i in self.members
        }
        bylabel = defaultdict(list)
        for i, row, sl in zip(self.members, self.rows, self.slices, strict=True):
            bylabel[row["candidate_index"]].append((i, sl))
        self.blocks = []
        for j, items in bylabel.items():
            positions = np.concatenate([np.arange(sl.start, sl.stop) for _, sl in items])
            n = len(positions)
            cov = np.eye(n) * 150**2
            shared = np.zeros((n, n))
            cursor = 0
            group_positions = defaultdict(list)
            for i, sl in items:
                count = sl.stop - sl.start
                use = np.arange(cursor, cursor + count)
                cursor += count
                cov[np.ix_(use, use)] += self.member_bias_sigmas[i] ** 2
                if i in self.linked_group:
                    group_positions[self.linked_group[i]].extend(use)
            for use in group_positions.values():
                shared[np.ix_(use, use)] += 1000**2 - independent_sigma**2
            cov += shared
            lower = np.linalg.cholesky(cov)
            inverse = np.linalg.solve(lower, np.eye(n))
            self.blocks.append(
                dict(
                    candidate=j,
                    positions=positions,
                    inverse=inverse,
                    shared=shared,
                    logvolume=float(2 * np.log(np.diag(lower) / 150).sum()),
                    covariance=cov,
                )
            )
        self.ready = True

    def bias_sigma_for_member(self, i):
        return self.member_bias_sigmas[i]

    def calculate(self, x):
        state = self.decode(x)
        f, e = AnchoredFamilies.predicted(self, x)
        raw = np.empty(len(self.flat_times))
        q = np.empty(len(raw))
        for i, sl, alias in zip(self.members, self.slices, self.alias, strict=True):
            t = self.scan.tracks[i]
            q[sl] = t["rf_hz"] / 11.5e9
            raw[sl] = (
                t["values"] + alias * PERIOD - self.scan.hardware(t, state["beta"]) - q[sl] * f[sl]
            )
            if self.method == "receiver_smooth":
                raw[sl] -= q[sl] * (self.scan.rx_basis[i] @ state["smooth"][t["receiver"] - 1])
        residuals = [np.maximum(0, -e) / 2]
        stats = []
        correction = np.zeros(len(raw))
        for block in self.blocks:
            ix = block["positions"]
            white = block["inverse"] @ raw[ix]
            value = low_rank_marginal(
                white,
                np.zeros((len(ix), 0)),
                len(ix),
                degrees_of_freedom=4,
                base_logvolume=block["logvolume"],
            )
            residuals.append(value["residual"])
            correction[ix] = block["shared"] @ (block["inverse"].T @ white)
            stats.append(
                dict(
                    norad=int(self.scan.norads[block["candidate"]]),
                    points=len(ix),
                    cost=float(value["residual"] @ value["residual"]),
                )
            )
        residuals.extend(
            (state["beta"][4:8] / 75, state["phases"][self.labels] / self.scan.sigma[self.labels])
        )
        for extra in state["extra"].values():
            residuals.append(extra / (10 if self.method == "family_rate" else 1e-4))
        if self.method == "receiver_smooth":
            residuals.append(state["smooth"].ravel() / 200)
        return np.concatenate(residuals), stats, f, e, correction, q

    def residual(self, x, *, details=False):
        r, stats, *_ = self.calculate(x)
        return (r, stats) if details else r

    def predicted(self, x):
        if not self.ready:
            return AnchoredFamilies.predicted(self, x)
        _, _, f, e, correction, q = self.calculate(x)
        return f + correction / q, e


def frame_problem(*args, independent_sigma):
    return restore_radio_initialization(
        ReceiverDriftProblem(
            FrameBiasFamilies(*args, independent_sigma=independent_sigma), mean_sigma=10
        )
    )


def run(case, method):
    directory = OUTPUT / "frame_bias" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source_name, pair = choose_pair(incumbents(case, method))
    seed = pair["c0"]
    anchor = seed["east_north_km"]
    scan = Scan(case)
    links, metadata = linked_tracks(scan, seed)
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            input_c0_incumbent=source_name,
            independent_frame_timing_links_require_at_least_3_pairs=True,
            identical_satellite_hypothesis_required_for_this_covariance_only_prototype=True,
            unchanged_marginal_bias_variance_hz2=1000**2,
            independent_bias_sigmas_hz=[1000, 300, 100],
            no_observation_or_pair_factor_double_counting=True,
            no_new_fitted_bias_coordinates=True,
            same_curved_points_aliases_priors_and_c0_grid_starts_for_c_arms=True,
            marginal_covariance_logvolume_penalty_included=True,
            source_clock_correlation_is_hypothesis=True,
            linked_tracks=[[scan.tracks[i]["key"] for i in g] for g in links],
            metadata=metadata,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for sigma in (1000.0, 300.0, 100.0):
        name = f"independent_sigma_{sigma:g}"
        if all(f"{name}/{a}" in results for a in ("c0", "fitted_c")):
            continue

        def factory(*args, s=sigma):
            p = frame_problem(*args, independent_sigma=s)
            lock_aliases(p, seed["aliases"])
            return p

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        for arm, fit in fits.items():
            results[f"{name}/{arm}"] = fit
        write(path, results)
        print(case, method, name, {a: f["east_north_km"] for a, f in fits.items()}, flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument(
        "--method", choices=["shared_phase", "receiver_smooth"], default="receiver_smooth"
    )
    a = p.parse_args()
    run(a.case, a.method)
