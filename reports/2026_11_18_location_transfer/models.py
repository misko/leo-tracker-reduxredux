"""Replay the published regional models in an explicitly supplied geographic tile."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PILOTS = HERE.parent / "2026_11_18_embedded_prototypes"
sys.path[:0] = [str(PILOTS), str(PILOTS / "06_coreset"), str(PILOTS / "10_network")]
import bench
import cold_replay as cold
import coreset
import network
from shape_refinement import doppler_peak

CONFIG = json.loads((HERE / "protocol.json").read_bytes())
ARMS = CONFIG["fit_arms"]
WEIGHTS = np.load(PILOTS / "10_network/weights.npy", allow_pickle=False)


def latlon(center, xy):
    lat = center[0] + float(xy[1]) / 111.
    lon = center[1] + float(xy[0]) / (111.32 * np.cos(np.deg2rad(center[0])))
    return [lat, (lon + 180.) % 360. - 180.]


@contextmanager
def tile(center):
    # Frozen code reads a module constant in observer(). Each replay runs serially.
    previous = cold.CENTER
    cold.CENTER = tuple(center)
    try:
        yield
    finally:
        cold.CENTER = previous


def identity(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=1, allow_nan=False) + "\n")


def declined():
    return {arm: {"status": "insufficient"} for arm in ARMS}


def physics_fit(data, bias, selected, center):
    if len(selected) < 4:
        return dict(arms=declined(), assignments=[])
    d = coreset.take(data, selected)
    score, start, winners, loss = cold.grid_vote(d, bias)
    kept = np.flatnonzero(loss < coreset.INLIER_COST_LIMIT)
    arms = {}
    for arm in ARMS:
        fit = cold.solve(d, kept, winners, bias, start, fitted_c=arm == "fitted_c")
        if fit["status"] == "estimate":
            fit["latlon"] = latlon(center, fit["xy"])
        arms[arm] = fit
    assigned = [[int(d["ti"][i]), int(d["ids"][i, winners[i]])] for i in kept]
    return dict(arms=arms, grid_score=float(score), assignments=assigned)


def oracle_fit(d, bias, owners, center):
    kept, columns = [], []
    for i, ti in enumerate(d["ti"]):
        expected = owners[int(ti)]
        matches = np.flatnonzero(d["ids"][i] == expected)
        if len(matches):
            kept.append(i)
            columns.append(int(matches[0]))
    if not kept:
        return dict(arms=declined(), assignments=[])
    known = coreset.take(d, kept)
    idx = np.arange(len(kept))
    for key in ("ids", "raw", "mean", "cov"):
        known[key] = known[key][idx, columns][:, None]
    return physics_fit(known, bias, idx, center)


def fixed_budget(d, bias):
    seed = CONFIG["seed"]
    order = sorted(range(len(d["ti"])), key=lambda i: hashlib.sha256(
        f"{seed}/{int(d['ti'][i])}".encode()).digest())
    return dict(geometry12=coreset.select_tracks(d, bias)[0], full=np.arange(len(order)),
                longest12=coreset.longest_tracks(d), random12=np.array(order[:12]))


def run_models(graph, bank, center, owners=None, refine=False):
    d = cold.descriptors(graph, bank)
    result = {}
    if d is None:
        for method in ("geometry12", "full", "longest12", "random12"):
            result[method] = dict(arms=declined(), assignments=[])
        if owners is not None:
            result["known_ids"] = dict(arms=declined(), assignments=[])
    else:
        bias = cold.bias_vote(d)
        for method, selected in fixed_budget(d, bias).items():
            result[method] = physics_fit(d, bias, selected, center)
        if owners is not None:
            result["known_ids"] = oracle_fit(d, bias, owners, center)
    evidence = network.evidence(graph, bank)
    shape_methods = ("coordinate_network", "shape_grid", "refined_shape") if refine else ("coordinate_network", "shape_grid")
    for method in shape_methods:
        if evidence is None:
            result[method] = dict(arms=declined())
            continue
        features, field, rows = evidence
        if method == "coordinate_network":
            xy = network.predict(WEIGHTS, features.astype(np.float32))
        elif method == "refined_shape":
            xy = doppler_peak(network,field,rows)
        else:
            xy = network.GRID[np.argmax(field)]
        rms, _ = network.shape_rms(xy, rows)
        fit = dict(status="estimate", xy=xy.tolist(), latlon=latlon(center, xy), rms_hz=rms)
        result[method] = dict(arms={a: fit for a in ARMS})
    prior = dict(status="estimate", xy=[0., 0.], latlon=list(center), rms_hz=None)
    result["prior_center"] = dict(arms={a: prior for a in ARMS})
    if owners is not None:
        # Simulator labels start here; the blind predictions are already complete.
        for method in ("geometry12", "full", "longest12", "random12", "known_ids"):
            assigned = result[method]["assignments"]
            clean = [(ti, sat) for ti, sat in assigned if owners[ti] is not None]
            result[method]["clean_assigned"] = len(clean)
            result[method]["correct_clean_ids"] = sum(sat == owners[ti] for ti, sat in clean)
    for entry in result.values():
        entry.pop("assignments", None)
    return result


def whole_track_split(graph):
    train, test = [], []
    for i in graph["curved_indices"]:
        t = graph["tracks"][i]["times"]
        if t[-1] <= 150.:
            train.append(i)
        elif t[0] >= 150.:
            test.append(i)
    return [dict(tracks=graph["tracks"], curved_indices=indices) for indices in (train, test)]


def held_out_contest(graph, bank, center):
    train, test = whole_track_split(graph)
    train_d = cold.descriptors(train, bank)
    test_d = cold.descriptors(test, bank)
    count = min(64, len(test["curved_indices"]))
    result = {}
    if train_d is None or test_d is None or count == 0:
        return dict(train_tracks=len(train["curved_indices"]), held_tracks=count, scores=result)
    bias = cold.bias_vote(train_d)
    for method in ("geometry12", "full"):
        indices = (coreset.select_tracks(train_d, bias)[0] if method == "geometry12"
                   else np.arange(len(train_d["ti"])))
        fit = physics_fit(train_d, bias, indices, center)
        scores = {}
        for arm, estimate in fit["arms"].items():
            if estimate["status"] != "estimate":
                scores[arm] = None
                continue
            x, y = estimate["xy"]
            cost = cold.phase_cost(test_d["mean"], test_d["cov"], x, y, 0., shape_only=True)
            scores[arm] = float((1 / (1 + cost.min(axis=1)/4)).sum() / count)
        result[method] = scores
    return dict(train_tracks=len(train["curved_indices"]), held_tracks=count, scores=result)
