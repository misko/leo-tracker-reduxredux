"""Bounded leave-family-fold-out receiver localization on anonymous DS26 tracks."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, PANEL, latlon
import cold_replay as cold


ARMS = ("c0", "fitted_c")
FOLDS = 4
IRLS_STEPS = 4
SCORE_CAP = 9.0
HALF_WIDTH = PANEL["box_width_km"] / 2
SHARED = 11
RADIO_SCALE = np.array([HALF_WIDTH, HALF_WIDTH, *([32000.] * 4), *([750.] * 4),
                        200000., cold.PHASE_SD_S])
POSITION_PRECISION = (HALF_WIDTH / 1000.) ** 2


@dataclass
class Tracks:
    group: np.ndarray
    rf: np.ndarray
    times: np.ndarray
    raw: np.ndarray
    ids: np.ndarray

    def subset(self, rows):
        return Tracks(self.group[rows], self.rf[rows], self.times[rows],
                      self.raw[rows], self.ids[rows])


@dataclass
class Stats:
    grams: np.ndarray
    absolute_grams: np.ndarray
    ids: np.ndarray
    family: np.ndarray
    counts: np.ndarray
    design_rank: int


def candidate_tracks(d, winners, selected):
    choices = winners[selected]
    return Tracks(d["group"][selected], d["rf"][selected], d["t"][selected],
                  d["raw"][selected, choices], d["ids"][selected, choices])


def deduplicate(tracks):
    rows = []
    fingerprints = set()
    for row in range(len(tracks.ids)):
        key = (tracks.ids[row], tracks.group[row], tracks.rf[row],
               tracks.times[row].tobytes(), tracks.raw[row].tobytes())
        if key not in fingerprints:
            rows.append(row)
            fingerprints.add(key)
    return tracks.subset(rows)


def make_stats(tracks, bias, start):
    n, samples = tracks.raw.shape[:2]
    design = np.zeros((n, samples, SHARED + 2))
    design[:, :, :2] = tracks.raw[:, :, 1:3]
    design[np.arange(n), :, 2 + tracks.group] = 1.
    design[np.arange(n), :, 6 + tracks.group] = (tracks.times - 150.) / 150.
    design[:, :, 10] = tracks.rf[:, None]
    design[:, :, 11] = tracks.raw[:, :, 3]
    y = tracks.raw[:, :, 0] - bias[tracks.group, None]
    level = np.mean(y - design[:, :, :2] @ start, axis=1)
    design[:, :, 12] = y - (cold.PERIOD * np.rint(level / cold.PERIOD))[:, None]
    design[:, :, :12] *= RADIO_SCALE
    means = design.mean(axis=1, keepdims=True)
    shape = (design - means) / (cold.SHAPE_SD * np.sqrt(samples))
    level = means / cold.LEVEL_SD
    absolute_grams = np.einsum("nri,nrj->nij", design, design)
    grams = np.einsum("nri,nrj->nij", shape, shape) + np.einsum("nri,nrj->nij", level, level)
    ids, family, counts = np.unique(tracks.ids, return_inverse=True, return_counts=True)
    rf_design = np.column_stack((np.eye(4)[tracks.group], tracks.rf))
    rank = np.linalg.matrix_rank(rf_design) - len(np.unique(tracks.group))
    return Stats(grams, absolute_grams, ids, family, counts, int(rank))


def assign_folds(tracks, stats):
    """Spread strong within-track position gradients over equal-size family folds."""
    shape = tracks.raw[:, :, 1:4] - tracks.raw[:, :, 1:4].mean(axis=1, keepdims=True)
    info = np.einsum("nri,nrj->nij", shape, shape) / (cold.SAMPLES * cold.SHAPE_SD**2)
    phase_info = info[:, 2, 2] + cold.PHASE_SD_S**-2
    xy_info = info[:, :2, :2] - info[:, :2, 2, None] * info[:, None, 2, :2] / phase_info[:, None, None]
    family_info = np.zeros((len(stats.counts), 2, 2))
    np.add.at(family_info, stats.family, xy_info / stats.counts[stats.family, None, None])
    initial = np.eye(2) * .01
    leverage = np.linalg.slogdet(initial + family_info)[1]
    order = np.argsort(-leverage, kind="stable")
    count = min(FOLDS, len(stats.counts))
    folds = np.zeros(len(stats.counts), dtype=int)
    used = np.zeros(count, dtype=int)
    geometry = np.repeat(initial[None, :, :], count, axis=0)
    for member in order:
        gain = np.linalg.slogdet(geometry + family_info[member])[1] - np.linalg.slogdet(geometry)[1]
        fold = int(np.argmax(np.where(used == used.min(), gain, -np.inf)))
        folds[member] = fold
        used[fold] += 1
        geometry[fold] += family_info[member]
    return folds


def aggregate(stats, weights):
    matrices = np.zeros((len(stats.counts), *stats.grams.shape[1:]))
    np.add.at(matrices, stats.family, stats.grams * weights[:, None, None])
    return matrices


def bounded_quadratic(info, rhs):
    """Minimize a positive definite two-variable quadratic on [-1, 1]^2."""
    xy = np.linalg.solve(info, rhs)
    if np.max(np.abs(xy)) <= 1.:
        return xy
    candidates = []
    for fixed in (0, 1):
        other = 1 - fixed
        for edge in (-1., 1.):
            xy = np.zeros(2)
            xy[fixed] = edge
            xy[other] = np.clip((rhs[other] - info[other, fixed] * edge) / info[other, other], -1., 1.)
            candidates.append(xy)
    return min(candidates, key=lambda point: .5 * point @ info @ point - rhs @ point)


def profile_phase(matrices, beta):
    return (matrices[:, SHARED, -1] - matrices[:, SHARED, :SHARED] @ beta) / (1. + matrices[:, SHARED, SHARED])


def track_error(grams, stats, beta, phase):
    coefficients = np.column_stack((np.broadcast_to(beta, (len(stats.family), SHARED)),
                                    phase[stats.family], -np.ones(len(stats.family))))
    return np.maximum(0., np.einsum("ni,nij,nj->n", coefficients, grams, coefficients))


def fit(stats, include, fitted):
    """Four track IRLS updates, with scalar family timing eliminated by Schur complements."""
    columns = SHARED if fitted else SHARED - 1
    family_weights = include[stats.family] / stats.counts[stats.family]
    weights = family_weights
    beta = np.zeros(SHARED)
    prior = np.eye(columns)
    prior[0, 0] = prior[1, 1] = POSITION_PRECISION
    for _ in range(IRLS_STEPS):
        matrices = aggregate(stats, weights)
        denom = 1. + matrices[:, SHARED, SHARED]
        cross = matrices[:, :columns, SHARED]
        hessian = matrices[:, :columns, :columns].sum(axis=0) + prior - cross.T @ (cross / denom[:, None])
        hessian = (hessian + hessian.T) * .5
        rhs = matrices[:, :columns, -1].sum(axis=0) - cross.T @ (matrices[:, SHARED, -1] / denom)
        # Eliminate receiver coefficients before choosing the bounded x/y optimum.
        nuisance = np.linalg.solve(hessian[2:, 2:], np.column_stack((hessian[2:, :2], rhs[2:])))
        xy_information = hessian[:2, :2] - hessian[:2, 2:] @ nuisance[:, :2]
        xy_rhs = rhs[:2] - hessian[:2, 2:] @ nuisance[:, 2]
        beta[:2] = bounded_quadratic(xy_information, xy_rhs)
        beta[2:columns] = nuisance[:, 2] - nuisance[:, :2] @ beta[:2]
        phase = profile_phase(matrices, beta)
        error = track_error(stats.grams, stats, beta, phase)
        weights = family_weights * np.minimum(1., 2.5 / np.maximum(.01, np.sqrt(error)))
    return beta


def validate(stats, matrices, beta):
    """Assign one capped score per family, including out-of-fold families."""
    phase = profile_phase(matrices, beta)
    track = track_error(stats.grams, stats, beta, phase)
    loss = np.array([np.median(track[stats.family == i]) for i in range(len(matrices))]) + phase**2
    return loss, phase


def estimate(stats, folds, fitted):
    distinct = len(stats.counts)
    all_families = np.ones(distinct, dtype=bool)
    across_families = aggregate(stats, 1. / stats.counts[stats.family])
    subsets = [(None, all_families)]
    for fold in np.unique(folds):
        include = folds != fold
        if np.count_nonzero(include) >= 3 and stats.counts[include].sum() >= 4:
            subsets.append((int(fold), include))

    best_score, best_beta, best_loss = np.inf, None, None
    winning_fold = None
    for fold, include in subsets:
        beta = fit(stats, include, fitted)
        loss, _ = validate(stats, across_families, beta)
        score = float(np.minimum(SCORE_CAP, loss).sum())
        if score < best_score:
            best_score, best_beta, best_loss = score, beta, loss
            winning_fold = fold
    inliers = best_loss < SCORE_CAP
    refined = np.count_nonzero(inliers) >= 3 and stats.counts[inliers].sum() >= 4
    if not refined:
        return dict(status="abstain", reason="too_few_independent_inlier_families",
                    proposals=len(subsets), inlier_families=int(np.count_nonzero(inliers)))
    beta = fit(stats, inliers, fitted)
    loss, phase = validate(stats, across_families, beta)
    score = float(np.minimum(SCORE_CAP, loss).sum())
    refit_kept = score <= best_score
    if not refit_kept:
        beta = best_beta
        loss, phase = validate(stats, across_families, beta)
        score = best_score
    inliers = loss < SCORE_CAP
    if np.count_nonzero(inliers) < 3 or stats.counts[inliers].sum() < 4:
        return dict(status="abstain", reason="too_few_independent_inlier_families_after_refit",
                    proposals=len(subsets), inlier_families=int(np.count_nonzero(inliers)))
    squared = track_error(stats.absolute_grams, stats, beta, phase) / cold.SAMPLES
    xy = beta[:2] * HALF_WIDTH
    return dict(status="estimate", latlon=latlon(xy), xy_km=xy.tolist(),
                rms_hz=float(np.sqrt(squared.mean())),
                rms_inlier_hz=float(np.sqrt(squared[inliers[stats.family]].mean())),
                consensus_loss_per_family=score / distinct,
                tracks=len(stats.family), satellites=distinct,
                inlier_families=int(np.count_nonzero(inliers)),
                rejected_catalog_ids=stats.ids[~inliers].tolist(),
                inlier_tracks=int(stats.counts[inliers].sum()), proposals=len(subsets),
                winning_omitted_fold=winning_fold,
                refit_kept=bool(refit_kept), c_hz_per_ghz=float(beta[10] * RADIO_SCALE[10]),
                rf_column_independent_of_lane_offsets=bool(stats.design_rank),
                on_boundary=bool(np.max(np.abs(xy)) > HALF_WIDTH - .01))


def run_consensus(tracks, bias, xy):
    unique = deduplicate(tracks)
    if len(unique.ids) < 4 or len(np.unique(unique.ids)) < 3:
        result = dict(status="abstain", reason="too_few_tracks_or_families")
        return {arm: result for arm in ARMS}, {}
    stats = make_stats(unique, bias, xy)
    folds = assign_folds(unique, stats)
    arms = {arm: estimate(stats, folds, fitted=(arm == "fitted_c")) for arm in ARMS}
    cost = dict(unique_tracks=len(unique.ids), family_count=len(folds),
                families_per_fold=np.bincount(folds).tolist(),
                gram_arrays_bytes=stats.grams.nbytes + stats.absolute_grams.nbytes,
                max_shared_solve_dimension=SHARED - 2)
    return arms, cost


def compact(d, selected, winners, bias, xy):
    arms = {}
    for arm in ARMS:
        result = cold.solve(d, selected, winners, bias, xy, fitted_c=(arm == "fitted_c"))
        if result["status"] == "estimate":
            result["latlon"] = latlon(result.pop("xy"))
        else:
            result = dict(status="abstain", reason=result["status"])
        arms[arm] = result
    return arms


def duplicate_check(tracks, bias, xy, reference):
    counts = np.unique(tracks.ids, return_counts=True)
    family = counts[0][np.argmax(counts[1])]
    repeated = np.flatnonzero(tracks.ids == family)
    rows = np.r_[np.arange(len(tracks.ids)), np.tile(repeated, 5)]
    replay, _ = run_consensus(tracks.subset(rows), bias, xy)
    assert replay == reference
    return dict(pass_exact=True, repeated_family=int(family), copies_added=5,
                rows_added=int(len(rows) - len(tracks.ids)))


def outlier_check(d, selected, winners, tracks, bias, xy, clean, clean_baseline, family):
    """Inject alternating CFO error into the same whole family after shortlisting."""
    is_family = tracks.ids == family
    bad_rows = selected[is_family]
    corrupted = dict(d, raw=d["raw"].copy())
    size_hz = 6000.
    corrupted["raw"][bad_rows, winners[bad_rows], :, 0] += size_hz * (-1) ** np.arange(cold.SAMPLES)
    bad_tracks = candidate_tracks(corrupted, winners, selected)
    arms, _ = run_consensus(bad_tracks, bias, xy)
    baseline = compact(corrupted, selected, winners, bias, xy)

    def shift(a, b):
        if a["status"] != "estimate" or b["status"] != "estimate":
            return None
        deltas = np.subtract(a["latlon"], b["latlon"])
        scales = [111., 111.32 * np.cos(np.deg2rad(PANEL["search_center_latlon"][0]))]
        return float(np.linalg.norm(deltas * scales))

    return dict(family=family, perturbed_tracks=len(bad_rows), alternating_sample_error_hz=size_hz,
                arms={arm: dict(consensus_status=arms[arm]["status"],
                                compact_status=baseline[arm]["status"],
                                family_rejected=family in arms[arm].get("rejected_catalog_ids", []),
                                winning_omitted_fold=arms[arm].get("winning_omitted_fold"),
                                consensus_shift_km=shift(arms[arm], clean[arm]),
                                compact_shift_km=shift(baseline[arm], clean_baseline[arm]))
                      for arm in ARMS})


def run_case(case):
    start = time.perf_counter()
    doc = cold.read(cold.GRAPHS / f"{case}.json")
    graph_read = time.perf_counter()
    bank, receipt = cold.build_bank(case, doc["metadata"], check_approximation=False)
    d = cold.descriptors(doc, bank)
    if d is None:
        arms = {arm: dict(status="abstain", reason="no_curved_tracks") for arm in ARMS}
        return dict(case=case, arms=arms, wall_s=time.perf_counter() - start), {}
    bias = cold.bias_vote(d)
    _, xy, winners, costs = cold.grid_vote(d, bias)
    selected = np.flatnonzero(costs < 12.)
    tracks = candidate_tracks(d, winners, selected)
    front_done = time.perf_counter()
    arms, cost = run_consensus(tracks, bias, xy)
    finish = time.perf_counter()
    baseline = compact(d, selected, winners, bias, xy)
    control_done = time.perf_counter()
    checks = {}
    if case == CASES[0]:
        duplicate = duplicate_check(tracks, bias, xy, arms)
        checks["duplicate_on_first_case"] = duplicate
        checks["gross_outlier_on_first_case"] = outlier_check(d, selected, winners, tracks, bias, xy,
                                                             arms, baseline, duplicate["repeated_family"])
    return dict(case=case, arms=arms, wall_s=finish-start,
                checks=dict(compact_same_tracks=baseline, compact_both_arms_wall_s=control_done-finish,
                            graph_read_wall_s=graph_read-start, common_frontend_wall_s=front_done-graph_read,
                            consensus_both_arms_wall_s=finish-front_done,
                            causal_tle_snapshot=receipt["snapshot"], curved_tracks_described=len(d["ti"]),
                            shortlisted_tracks=len(selected), **cost)), checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "result.json")
    args = parser.parse_args()
    cases, checks = [], {}
    for case in CASES:
        row, test = run_case(case)
        cases.append(row)
        checks.update(test)
        print(case, [row["arms"][arm]["status"] for arm in ARMS], f'{row["wall_s"]:.3f} s', flush=True)
    result = dict(
        method="Geometry-balanced leave-satellite-family-fold-out consensus",
        timing_scope=("Single-thread host Python wall time from reading the existing graph through both consensus arms. "
                      "Includes graph JSON decode, causal TLE propagation, descriptors and common grid vote. "
                      "Control and checks are measured separately. Excludes graph production, IQ, transport and device time."),
        cases=cases, checks=checks,
    )
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
