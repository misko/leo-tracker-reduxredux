"""Bounded position grid with anonymous satellite and clutter mixtures."""

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from scipy.special import logsumexp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bench
import cold_replay as cold


COARSE_STEPS = 7
PARENTS = 4
EM_UPDATES = 5
CLUTTER_LOG_EVIDENCE = math.log(0.15) - 6.0
ARM_NAMES = ("c0", "fitted_c")
HALF_WIDTH_KM = bench.PANEL["box_width_km"] / 2
MODE_DISTANCE_KM = 5.0


@dataclass(frozen=True)
class Cell:
    xy: tuple[float, float]
    width: float
    score: float
    calibration: np.ndarray
    depth: int


class Mixture:
    """Integrate Gaussian track timing, sum identities and profile shared calibration."""

    def __init__(self, d, bias, fitted):
        self.d = d
        self.lane_bias = np.asarray(bias)
        self.center = self.lane_bias[d["group"]][:, None]
        self.design = np.eye(4)[d["group"]] * 32_000.0
        if fitted:
            self.design = np.column_stack((self.design, d["rf"] * 200_000.0))
        self.a = cold.SHAPE_SD**-2
        self.b = cold.LEVEL_SD**-2
        self.slope = d["mean"][..., 3]
        self.curvature = (self.a * d["cov"][..., 3, 3] + self.b * self.slope**2
                          + cold.PHASE_SD_S**-2)
        self.effective_b = self.b * (1.0 - self.b * self.slope**2 / self.curvature)
        self.log_det = np.log(self.curvature * cold.PHASE_SD_S**2)
        self.candidate_log_prior = math.log(0.85 / self.slope.shape[1])

    def position_terms(self, xy):
        x, y = xy
        mean, cov = self.d["mean"], self.d["cov"]
        level = mean[..., 0] - x * mean[..., 1] - y * mean[..., 2] - self.center
        cross = cov[..., 0, 3] - x * cov[..., 1, 3] - y * cov[..., 2, 3]
        var = (cov[..., 0, 0] - 2*x*cov[..., 0, 1] - 2*y*cov[..., 0, 2]
               + x*x*cov[..., 1, 1] + 2*x*y*cov[..., 1, 2] + y*y*cov[..., 2, 2])
        return level, self.a * cross, self.a * var

    def components(self, terms, calibration):
        level, cross, var = terms
        residual = cold.wrap(level - (self.design @ calibration)[:, None])
        numerator = cross + self.b * self.slope * residual
        phase = numerator / self.curvature
        chi = np.maximum(0.0, var + self.b * residual**2 - numerator * phase)
        components = self.candidate_log_prior - 0.5 * (chi + self.log_det)
        evidence = np.logaddexp(CLUTTER_LOG_EVIDENCE, logsumexp(components, axis=1))
        return residual, phase, components, evidence

    def fit(self, xy, width, depth):
        terms = self.position_terms(xy)
        calibration = np.zeros(self.design.shape[1])
        identity = np.eye(len(calibration))
        for _ in range(EM_UPDATES):
            residual, phase, components, evidence = self.components(terms, calibration)
            weight = np.exp(components - evidence[:, None])
            precision = np.sum(weight * self.effective_b, axis=1)
            score_gradient = np.sum(weight * self.b * (residual - self.slope * phase), axis=1)
            normal = identity + self.design.T @ (precision[:, None] * self.design)
            direction = self.design.T @ score_gradient - calibration
            calibration += np.linalg.solve(normal, direction)
        _, _, _, evidence = self.components(terms, calibration)
        score = float(evidence.sum() - 0.5 * (calibration @ calibration))
        return Cell(xy, width, score, calibration, depth)


def split_cell(model, parent):
    width = parent.width / 3
    return [Cell(parent.xy, width, parent.score, parent.calibration, parent.depth + 1)
            if (dx, dy) == (0, 0)
            else model.fit((parent.xy[0] + dx * width, parent.xy[1] + dy * width),
                           width, parent.depth + 1)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def search(model):
    width = 2 * HALF_WIDTH_KM / COARSE_STEPS
    centers = (np.arange(COARSE_STEPS) - COARSE_STEPS // 2) * width
    start = time.perf_counter()
    coarse = [model.fit((float(x), float(y)), width, 0) for x in centers for y in centers]
    coarse_s = time.perf_counter() - start
    parents = []
    for cell in sorted(coarse, key=lambda cell: -cell.score):
        if all(math.dist(cell.xy, parent.xy) >= 2 * width - 1e-9 for parent in parents):
            parents.append(cell)
        if len(parents) == PARENTS:
            break
    assert len(parents) == PARENTS
    parent_xy = {parent.xy for parent in parents}
    leaves = [cell for cell in coarse if cell.xy not in parent_xy]
    for parent in parents:
        children = split_cell(model, parent)
        advance = max(children, key=lambda cell: cell.score)
        leaves.extend(child for child in children if child is not advance)
        leaves.extend(split_cell(model, advance))
    return coarse, leaves, coarse_s


def ambiguity(cells, winner):
    remote = max((cell for cell in cells if math.dist(cell.xy, winner.xy) >= MODE_DISTANCE_KM),
                 key=lambda cell: cell.score, default=None)
    near_top = sum(cell.width**2 for cell in cells if cell.score >= winner.score - 2.0)
    return dict(within_two_score_units_area_km2=near_top,
                remote_gap=None if remote is None else winner.score - remote.score,
                remote_xy_km=None if remote is None else remote.xy,
                remote_distance_km=None if remote is None else math.dist(remote.xy, winner.xy),
                winner_cell_width_km=winner.width,
                winner_cell_touches_box=any(abs(c) + winner.width / 2 >= HALF_WIDTH_KM - 1e-9
                                            for c in winner.xy))


def endpoint(model, cell):
    _, phase, components, evidence = model.components(model.position_terms(cell.xy), cell.calibration)
    choice = np.argmax(components, axis=1)
    rows = np.flatnonzero(np.max(components, axis=1) > CLUTTER_LOG_EVIDENCE)
    ids = model.d["ids"][rows, choice[rows]]
    calibration_hz = (model.center[:, 0] + model.design @ cell.calibration)[rows]
    raw = model.d["raw"][rows, choice[rows]]
    x, y = cell.xy
    residual = (raw[..., 0] - x * raw[..., 1] - y * raw[..., 2]
                - phase[rows, choice[rows], None] * raw[..., 3] - calibration_hz[:, None])
    residual -= cold.PERIOD * np.rint(residual.mean(axis=1, keepdims=True) / cold.PERIOD)
    fit_rows = {(int(model.d["ti"][i]), int(sat)): row for i, sat, row in zip(rows, ids, residual, strict=True)}
    result = dict(xy_km=cell.xy, score=cell.score, selected_tracks=len(rows),
                  selected_satellites=len(set(ids.tolist())),
                  mean_clutter_weight=float(np.mean(np.exp(CLUTTER_LOG_EVIDENCE - evidence))),
                  lane_offsets_hz=(model.lane_bias + cell.calibration[:4] * 32_000).tolist(),
                  c_hz_per_ghz=float(cell.calibration[4] * 200_000) if len(cell.calibration) == 5 else 0.0)
    if result["selected_tracks"] < 4 or result["selected_satellites"] < 3:
        return dict(status="abstain", reason="fewer than four selected tracks or three satellites", **result), fit_rows
    return dict(status="estimate", latlon=bench.latlon(cell.xy), rms_hz=float(np.sqrt(np.mean(residual**2))),
                rms_kind="selected absolute after marginal phase conditional mean", **result), fit_rows


def model_summary(model):
    start = time.perf_counter()
    coarse, leaves, coarse_s = search(model)
    best_coarse = max(coarse, key=lambda cell: cell.score)
    best = max(leaves, key=lambda cell: cell.score)
    result, selected = endpoint(model, best)
    coarse_result, _ = endpoint(model, best_coarse)
    return result, selected, dict(
        elapsed_s=time.perf_counter() - start, coarse_elapsed_s=coarse_s,
        cells_scored=len(leaves), coarse_cells_scored=len(coarse),
        candidate_terms_per_pass=int(model.slope.size), calibration_updates_per_cell=EM_UPDATES,
        candidate_terms_evaluated=int(model.slope.size) * (EM_UPDATES + 1) * len(leaves),
        coarse_only=coarse_result, coarse_ambiguity=ambiguity(coarse, best_coarse),
        refined_ambiguity=ambiguity(leaves, best),
        refinement_shift_km=math.dist(best.xy, best_coarse.xy),
        refinement_score_gain=best.score - best_coarse.score,
        coarse_cells=[[round(c.xy[0], 6), round(c.xy[1], 6), round(c.width, 6), round(c.score, 6)]
                      for c in coarse],
        final_cells=[[round(c.xy[0], 6), round(c.xy[1], 6), round(c.width, 6), round(c.score, 6)]
                     for c in leaves],
    )


def held_track_check(d):
    """Hold out every fourth track after sorting by its mean time; no refit on held tracks."""
    t_order = np.argsort(d["t"].mean(axis=1), kind="stable")
    held = t_order[3::4]
    train = np.setdiff1d(t_order, held)
    if not len(held):
        return dict(status="unavailable", reason="fewer than four descriptors")
    train_d, held_d = ({key: value[subset] for key, value in d.items()} for subset in (train, held))
    bias = cold.bias_vote(train_d)
    summary = dict(train_tracks=len(train), held_tracks=len(held), held_track_indexes=d["ti"][held].tolist())
    for fitted, arm in zip((False, True), ARM_NAMES, strict=True):
        train_model, held_model = (Mixture(data, bias, fitted) for data in (train_d, held_d))
        coarse, leaves, _ = search(train_model)
        summary[arm] = {}
        for key, cells in (("coarse", coarse), ("refined", leaves)):
            best = max(cells, key=lambda cell: cell.score)
            _, _, _, evidence = held_model.components(held_model.position_terms(best.xy), best.calibration)
            summary[arm][key] = dict(held_score_per_track=float(evidence.mean()),
                                     train_xy_km=best.xy, train_score=best.score)
    return summary


def case_replay(case):
    start = time.perf_counter()
    graph = cold.read(cold.GRAPHS / (case + ".json"))
    meta = graph["metadata"]
    if meta["alias_period_hz"] is not None:
        assert math.isclose(meta["alias_period_hz"], cold.PERIOD)
    loaded = time.perf_counter()
    bank, receipt = cold.build_bank(case, meta, check_approximation=False)
    banked = time.perf_counter()
    descriptors = cold.descriptors(graph, bank)
    result = dict(case=case, arms={})
    checks = dict(tle=receipt, graph_load_s=loaded - start, bank_build_s=banked - loaded,
                  bank_array_bytes=sum(v.nbytes for v in bank.values()),
                  observation_horizon_s=meta["duration_s"],
                  tle_cutoff_utc_ns=meta["causal_cutoff_utc_ns"],
                  graph_alias_period_hz=meta["alias_period_hz"], scoring_alias_period_hz=cold.PERIOD,
                  cold_fields=["anonymous curved graph tracks", "sample count", "local scan time",
                               "CFO", "receiver and side", "RF", "scan-start TLE cutoff"])
    if descriptors is None:
        result["arms"] = {arm: dict(status="abstain", reason="no qualifying track descriptors")
                          for arm in ARM_NAMES}
        result["wall_s"] = time.perf_counter() - start
        return result, checks
    d = descriptors
    bias = cold.bias_vote(d)
    checks.update(descriptor_and_bias_s=time.perf_counter() - banked, tracks=len(d["ti"]),
                  candidate_pairs=int(d["ids"].size), descriptor_array_bytes=sum(v.nbytes for v in d.values()),
                  samples_per_track=cold.SAMPLES, initial_lane_bias_hz=bias.tolist())
    selections = []
    for fitted, arm in zip((False, True), ARM_NAMES, strict=True):
        result["arms"][arm], selection, checks[arm] = model_summary(Mixture(d, bias, fitted))
        selections.append(selection)
    paired = sorted(set(selections[0]) & set(selections[1]))
    checks["paired_rms"] = dict(same_track_same_satellite=len(paired), **{
        arm: float(np.sqrt(np.mean(np.square([selected[key] for key in paired])))) if paired else None
        for arm, selected in zip(ARM_NAMES, selections, strict=True)})
    result["wall_s"] = time.perf_counter() - start
    holdout_start = time.perf_counter()
    checks["held_track_check"] = held_track_check(d)
    checks["held_track_check_s"] = time.perf_counter() - holdout_start
    return result, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("result.json"))
    args = parser.parse_args()
    from test_grid import run_checks

    outcome = dict(method="coarse-to-fine marginalized position grid", cases=[], checks=dict(
        numerical=run_checks(), case_checks={}, sampled_cell_columns=["east_km", "north_km", "width_km", "score"],
        score_kind="profile log mixture with Gaussian calibration penalty; relative diagnostic",
        primary_grid=dict(coarse_per_axis=COARSE_STEPS, refined_parents=PARENTS, split_per_axis=3,
                          refinement_levels=2, cells_per_arm=COARSE_STEPS**2 + PARENTS*2*8),
        coarse_only_control="same first-stage evaluations and model, with no refinement",
        held_track_check_scope="disjoint whole tracks from same full-scan upstream graph; frozen fit on held tracks"),
        timing_scope="single-thread host wall time for graph read, causal TLE bank, descriptors, shared bias vote, "
                     "both primary and reused coarse-only grid results, and paired diagnostics. Holdout timed separately.")
    for case in bench.CASES:
        result, checks = case_replay(case)
        outcome["cases"].append(result)
        outcome["checks"]["case_checks"][case] = checks
        print(case, {arm: row["status"] for arm, row in result["arms"].items()}, flush=True)
    args.output.write_text(json.dumps(outcome, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
