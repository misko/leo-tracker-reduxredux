"""End-of-scan DS26 replay with a nuisance-aware 12-track coreset."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench import CASES, latlon
import cold_replay as cold


LIMIT = 12
SURROGATE_CANDIDATES = 3
INLIER_COST_LIMIT = 12.
HORIZONTAL_PRIOR_SD_KM = 10.
NUISANCE_PRIOR_SD = np.array([32000.] * 4 + [750.] * 4 + [200000.])
ARMS = ("c0", "fitted_c")


def receiver_design(d, raw, fitted_c):
    """Derivatives of the common fit with horizontal, receiver and RF columns."""
    lane = np.eye(4)[d["group"]][:, None, None, :]
    design = np.empty((*raw.shape[:-1], 10 + int(fitted_c)))
    design[..., :2] = raw[..., 1:3]
    design[..., 2:6] = lane
    design[..., 6:10] = lane * (d["t"][:, None, :, None] - 150.) / 150.
    if fitted_c:
        design[..., 10] = d["rf"][:, None, None]
    return design


def whiten(design):
    """Use one track-level mean and a shape contribution normalized by length."""
    mean = design.mean(axis=-2, keepdims=True)
    shape = (design - mean) / (cold.SHAPE_SD * np.sqrt(cold.SAMPLES))
    return np.concatenate((shape, mean / cold.LEVEL_SD), axis=-2)


def track_information(d, bias):
    """Average local information over three central association hypotheses."""
    cost = cold.phase_cost(d["mean"], d["cov"], 0., 0., bias[d["group"], None])
    options = np.argsort(cost, axis=1, kind="stable")[:, :SURROGATE_CANDIDATES]
    row = np.arange(len(cost))[:, None]
    raw = d["raw"][row, options]
    cost = cost[row, options]
    relative = np.exp(-0.5 * (cost - cost[:, :1]))
    probability = relative / relative.sum(axis=1, keepdims=True)
    weight = probability / (1. + cost / 4.)

    a = whiten(receiver_design(d, raw, fitted_c=True))
    phase = whiten(raw[..., 3:4])[..., 0]
    normal = np.einsum("nksd,nkse->nkde", a, a)
    cross = np.einsum("nksd,nks->nkd", a, phase)
    phase_information = np.sum(phase**2, axis=-1) + cold.PHASE_SD_S**-2
    local = normal - np.einsum("nkd,nke,nk->nkde", cross, cross, 1. / phase_information)
    return np.einsum("nk,nkde->nde", weight, local), d["ids"][row[:, 0], options[:, 0]]


def horizontal_information(matrix):
    """Take the Schur complement of shared receiver and RF nuisance columns."""
    cross = matrix[..., 2:, :2]
    adjustment = np.swapaxes(cross, -1, -2) @ np.linalg.solve(matrix[..., 2:, 2:], cross)
    return matrix[..., :2, :2] - adjustment


def select_tracks(d, bias):
    blocks, owner = track_information(d, bias)
    information = np.diag(np.r_[[HORIZONTAL_PRIOR_SD_KM] * 2, NUISANCE_PRIOR_SD] ** -2)
    remaining = np.ones(len(owner), dtype=bool)
    unseen_lanes = set(d["group"].tolist())
    repeats = np.zeros(len(owner), dtype=int)
    chosen = []
    evaluated = 0
    for _ in range(min(LIMIT, len(owner))):
        eligible = remaining.copy()
        if unseen_lanes:
            eligible &= np.isin(d["group"], sorted(unseen_lanes))
        rows = np.flatnonzero(eligible)
        evaluated += len(rows)
        base = np.linalg.slogdet(horizontal_information(information))[1]
        hypothetical = horizontal_information(information + blocks[rows])
        gain = np.linalg.slogdet(hypothetical)[1] - base
        winner = rows[np.argmax(np.maximum(0., gain) / (1. + repeats[rows]))]
        chosen.append(winner)
        information += blocks[winner]
        remaining[winner] = False
        unseen_lanes.discard(d["group"][winner])
        repeats += owner == owner[winner]
    return np.asarray(chosen, dtype=int), owner, evaluated


def longest_tracks(d):
    return np.argsort(-d["span"], kind="stable")[:LIMIT]


def raw_fit_design(d, winners, fitted_c):
    raw = d["raw"][np.arange(len(winners)), winners][:, None]
    owners = d["ids"][np.arange(len(winners)), winners]
    satellites, family = np.unique(owners, return_inverse=True)
    one_hot = np.eye(len(satellites))[family]
    phase = raw[..., 3:4] * one_hot[:, None, None, :]
    return whiten(np.concatenate((receiver_design(d, raw, fitted_c), phase), axis=-1))[:, 0], owners


def unregularized_condition(design):
    """Profile observed nuisance columns, without priors or robust weights."""
    design = design.reshape(-1, design.shape[-1])
    horizontal, nuisance = design[:, :2], design[:, 2:]
    if len(horizontal) == 0:
        return dict(rank=0, condition=None, eigenvalues_km2_inverse=[0., 0.])
    scale = np.linalg.norm(nuisance, axis=0)
    nuisance = nuisance[:, scale > 0] / scale[scale > 0]
    u, singular, _ = np.linalg.svd(nuisance, full_matrices=False)
    if singular.size:
        u = u[:, singular > singular[0] * 1.e-10]
    reduced = horizontal - u @ (u.T @ horizontal)
    values = np.linalg.svd(reduced, compute_uv=False)
    tolerance = np.linalg.norm(horizontal, ord=2) * 1.e-8
    rank = int(np.count_nonzero(values > tolerance))
    values = np.pad(values, (0, 2 - len(values)))
    return dict(rank=rank, condition=float((values[0] / values[1]) ** 2) if rank == 2 else None,
                eigenvalues_km2_inverse=(values[::-1] ** 2).tolist())


def conditioning(d, winners):
    if not len(winners):
        return None
    output = {}
    for arm in ARMS:
        design, owners = raw_fit_design(d, winners, arm == "fitted_c")
        info = unregularized_condition(design)
        deletions = [unregularized_condition(design[owners != owner]) for owner in np.unique(owners)]
        info["leave_one_satellite_min_rank"] = min(row["rank"] for row in deletions)
        info["leave_one_satellite_min_eigenvalue_km2_inverse"] = min(
            row["eigenvalues_km2_inverse"][0] for row in deletions)
        output[arm] = info
    return output


def take(d, rows):
    return {key: value[rows] for key, value in d.items()}


def endpoint(d, inliers, winners, bias, start):
    arms = {}
    for arm in ARMS:
        fit = cold.solve(d, inliers, winners, bias, start, fitted_c=(arm == "fitted_c"))
        if fit["status"] == "estimate":
            fit["latlon"] = latlon(fit.pop("xy"))
        else:
            fit = dict(status="abstain", reason=fit["status"])
        arms[arm] = fit
    return arms


def replay_fit(d, rows, bias, shared_wall, selector_wall):
    begin = perf_counter()
    subset = take(d, rows)
    score, start, winners, losses = cold.grid_vote(subset, bias)
    grid_end = perf_counter()
    inliers = np.flatnonzero(losses < INLIER_COST_LIMIT)
    arms = endpoint(subset, inliers, winners, bias, start)
    fit_end = perf_counter()
    output = dict(arms=arms, logical_total_wall_s=shared_wall + selector_wall + fit_end - begin,
                  selector_wall_s=selector_wall, grid_wall_s=grid_end - begin, fit_wall_s=fit_end - grid_end,
                  grid_tracks=len(rows), grid_candidate_cells=49 * subset["ids"].size,
                  grid_descriptor_bytes=sum(a.nbytes for a in subset.values()),
                  inlier_fit_rows_per_irls_step=len(inliers) * (cold.SAMPLES + 1),
                  grid_score=float(score), grid_xy=list(start), grid_track_ids=subset["ti"].tolist(),
                  grid_lane_counts=np.bincount(subset["group"], minlength=4).tolist(),
                  retained_track_ids=subset["ti"][inliers].tolist(),
                  retained_satellites=subset["ids"][inliers, winners[inliers]].tolist())
    return output, subset, inliers, winners


def replay_case(case):
    begin = perf_counter()
    graph = cold.read(cold.GRAPHS / f"{case}.json")
    meta = graph["metadata"]
    read_end = perf_counter()
    bank, receipt = cold.build_bank(case, meta, check_approximation=False)
    bank_end = perf_counter()
    d = cold.descriptors(graph, bank)
    descriptor_end = perf_counter()
    if d is None:
        return dict(case=case, wall_s=descriptor_end - begin,
                    arms={arm: dict(status="abstain", reason="no_eligible_tracks") for arm in ARMS}), {}
    assert d["t"].max() <= meta["duration_s"] + 1.e-6
    bias = cold.bias_vote(d)
    shared_end = perf_counter()
    shared_wall = shared_end - begin

    chosen, owners, evaluated = select_tracks(d, bias)
    selector_wall = perf_counter() - shared_end
    primary = replay_fit(d, chosen, bias, shared_wall, selector_wall)

    start = perf_counter()
    longest = longest_tracks(d)
    longest_wall = perf_counter() - start
    longest_control = replay_fit(d, longest, bias, shared_wall, longest_wall)

    start = perf_counter()
    full = np.arange(len(d["ti"]))
    full_wall = perf_counter() - start
    full_control = replay_fit(d, full, bias, shared_wall, full_wall)

    comparison = {}
    for label, (result, subset, inliers, winners) in (
            ("geometry12", primary), ("longest12", longest_control), ("full", full_control)):
        result["conditioning"] = conditioning(take(subset, inliers), winners[inliers])
        comparison[label] = result
    comparison["geometry12"]["selection_provisional_satellites"] = owners[chosen].tolist()
    checks = dict(shared_wall_s=shared_wall, graph_read_wall_s=read_end - begin,
                  tle_bank_wall_s=bank_end - read_end, descriptor_wall_s=descriptor_end - bank_end,
                  bias_wall_s=shared_end - descriptor_end, shared_tracks=len(d["ti"]),
                  shared_bias_candidate_evaluations=82 * d["ids"].size,
                  selector_center_candidate_evaluations=d["ids"].size,
                  selector_information_blocks=SURROGATE_CANDIDATES * len(d["ti"]),
                  selector_candidate_set_evaluations=evaluated,
                  scan_duration_s=meta["duration_s"], latest_selected_input_s=float(d["t"].max()),
                  bank=receipt, comparison=comparison)
    main = comparison["geometry12"]
    return dict(case=case, wall_s=main["logical_total_wall_s"], arms=main["arms"]), checks


def self_check():
    """Twelve longest passes can have a completely unobserved second direction."""
    n = 14
    time = np.linspace(60., 110., cold.SAMPLES)
    raw = np.zeros((n, cold.K, cold.SAMPLES, 4))
    raw[:-1, :, :, 1] = 300. * np.sin(np.linspace(0., 2. * np.pi, cold.SAMPLES))
    raw[-1, :, :, 2] = raw[0, :, :, 1]
    mean, cov = cold.tile_stats(raw)
    d = dict(raw=raw, mean=mean, cov=cov, t=np.tile(time, (n, 1)), group=np.arange(n) % 4,
             rf=np.linspace(-.5, .5, n), ids=np.tile(np.arange(n)[:, None], (1, cold.K)),
             span=np.arange(n, 0, -1))
    chosen, _, _ = select_tracks(d, np.zeros(4))
    longest = longest_tracks(d)
    winner = np.zeros(LIMIT, dtype=int)
    selected_case = conditioning(take(d, chosen), winner)
    longest_case = conditioning(take(d, longest), winner)
    assert len(chosen) == len(set(chosen)) == LIMIT
    assert len(np.unique(d["group"][chosen])) == 4
    for arm in ARMS:
        assert selected_case[arm]["rank"] == 2
        assert longest_case[arm]["rank"] == 1
        assert selected_case[arm]["leave_one_satellite_min_rank"] == 1
    return dict(status="passed", geometry12=selected_case, longest12=longest_case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run only the synthetic rank counterexample")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("result.json"))
    args = parser.parse_args()
    check = self_check()
    if args.check:
        print(json.dumps(check, indent=2, allow_nan=False))
        return
    result = dict(method="receiver-nuisance-aware geometry coreset (12 tracks)",
                  timing_scope="one CPU thread, archived graph read through TLE bank, descriptors, common bias, "
                               "selection, grid and both robust endpoint fits, excluding controls and diagnostics",
                  cases=[], checks=dict(synthetic_observability=check, case_checks={}))
    for case in CASES:
        row, details = replay_case(case)
        result["cases"].append(row)
        result["checks"]["case_checks"][case] = details
        print(case, f"{row['wall_s']:.3f} s", {arm: model["status"] for arm, model in row["arms"].items()},
              flush=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
