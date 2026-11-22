"""Time and trace Graph track preparation on the declared saved detections."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from functools import wraps
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from leo.analysis import graph_tracklets as graph
from leo.analysis.localization_v3 import tracks
from leo.analysis import polynomial_tracklets as poly
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application.localization_v3_engine import _json_value
from tools.pipeline_eval.variants.experimental.graph_path import build, native_paths


def digest(value):
    return sha256(json.dumps(value, default=_json_value, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@contextmanager
def instrument(stage, routes, trace=False):
    def timed(name, operation):
        @wraps(operation)
        def call(*args, **kwargs):
            if name == "models" and (len(args) != 6 or kwargs):
                return operation(*args, **kwargs)
            start = process_time_ns()
            result = operation(*args, **kwargs)
            stage[name + "_ns"] += process_time_ns() - start
            stage[name + "_calls"] += 1
            if trace:
                if name == "topology":
                    routes.append(dict(edges=len(result[0]), topology=digest(result[:3]), paths=[]))
                elif name == "path":
                    path, _, edges, score = result
                    routes[-1]["paths"].append(dict(path=path, edges=edges, score=score))
                elif name == "models":
                    routes[-1]["paths"][-1]["models"] = [m["indices"] for m in result]
            return result

        return call

    with ExitStack() as stack:
        for module, field, name in (
            (tracks, "winning_observations", "winners"), (tracks, "fit_lane", "lanes"),
            (graph, "_graph", "topology"), (graph, "_best_path", "path"),
            (graph, "_path_models", "models"), (graph, "finish_lane", "finalize"),
        ):
            stack.enter_context(patch.object(module, field, timed(name, getattr(module, field))))
        yield


def run(document, cfg, *, trace=False):
    counts, routes = Counter(), []
    with instrument(counts, routes, trace=trace):
        start = process_time_ns()
        prepared = tracks.prepare_tracks(document, cfg)
        cpu = process_time_ns() - start
    result = dict(
        cpu_ns=cpu, stage=dict(counts), digest=digest(prepared),
        observations=len(prepared["observations"]), owned=prepared["graph_points"],
        track_count=len(prepared["tracks"]),
        curved_keys=[prepared["tracks"][i]["key"] for i in prepared["curved_indices"]],
    )
    if trace:
        result["routes"] = routes
    return prepared, result


def first_path_difference(base, candidate):
    for lane, (prior, following) in enumerate(zip(base, candidate, strict=True)):
        if prior["topology"] != following["topology"]:
            return dict(lane_ordinal=lane, event="topology")
        for rank, (a, b) in enumerate(zip(prior["paths"], following["paths"])):
            if any(not np.array_equal(a[name], b[name]) for name in ("path", "edges")):
                return dict(lane_ordinal=lane, path=rank, event="path", original=a, candidate=b)
            if digest(a.get("models")) != digest(b.get("models")):
                return dict(lane_ordinal=lane, path=rank, event="polynomial", original=a, candidate=b)
        if len(prior["paths"]) != len(following["paths"]):
            return dict(lane_ordinal=lane, path=min(len(prior["paths"]), len(following["paths"])),
                        event="path_count")
    return None


def selection_ranks(document):
    source = document["source"]
    ranks = {}
    for probe in source["probes"]:
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]
        selected = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
                       default=None)
        signature = probe["receiver_id"], probe["channel"], probe["valid_start_counter"]
        if signature in ranks:
            raise ValueError("Duplicate receiver opportunity")
        ranks[signature] = selected["candidate_rank"] if selected is not None else None
    return ranks


def membership_difference(left, right):
    def by_id(packet):
        return {row["observation_id"]: row for row in packet["observations"]}

    def owners(packet):
        return {oid: track["key"] for track in packet["tracks"] for oid in track["observation_ids"]}

    before, after = by_id(left), by_id(right)
    if before.keys() != after.keys():
        raise ValueError("The saved dense native inputs have different winning identities")
    if any(row["time_s"] != after[key]["time_s"] for key, row in before.items()):
        raise ValueError("The saved dense native inputs have different Graph timestamps")
    base, candidate = owners(left), owners(right)
    moves = {key: [base.get(key), candidate.get(key)] for key in before
             if base.get(key) != candidate.get(key)}
    rows = [dict(id=key, receiver=row["receiver"], channel=row["channel"], time_s=row["time_s"],
                 before_hz=row["measured_cfo_hz"], after_hz=after[key]["measured_cfo_hz"])
            for key, row in before.items() if row["measured_cfo_hz"] != after[key]["measured_cfo_hz"]]
    return dict(winner_changes=rows, membership_changes=moves)


def with_readouts(function, bindings, edits):
    source = getsource(function)
    for anchor, replacement in edits:
        if source.count(anchor) != 1:
            raise ValueError(f"Unexpected readout anchor in {function.__name__}")
        source = source.replace(anchor, replacement)
    namespace = dict(function.__globals__, **bindings)
    exec(compile(source, function.__code__.co_filename, "exec"), namespace)
    return namespace[function.__name__]


def trace_polynomials(t, y, cfg):
    notes, choices, costs = {}, [], []
    distances = {}
    stage = "proposal"

    def observe(name, value):
        notes[name] = value

    def arbitration_costs(number, indices, values):
        for index, distance in zip(indices, values, strict=True):
            distances.setdefault(int(index), []).append([number, float(distance)])

    traced_piece = with_readouts(poly._best_piece, {"tally": lambda d, c: costs.append([d, c])}, (
        ("        if cost < best_cost:", "        tally(degree, cost)\n        if cost < best_cost:"),
    ))
    traced_finish = with_readouts(graph.finish_lane, {
        "observe": observe, "arbitration_costs": arbitration_costs,
    }, (
        ("        take = (distance < gate)", "        arbitration_costs(number, ix, distance)\n"
         "        take = (distance < gate)"),
        ("    refined = []", '    observe("arbitration", owner.tolist())\n    refined = []'),
        ("    grouped = _repair_structured", '    observe("refined", [[p["degree"], p["indices"].tolist()]\n'
         '                        for p in refined])\n    grouped = _repair_structured'),
        ("    assignment, lifts =", '    observe("grouped", [[[p["degree"], p["indices"].tolist()]\n'
         '                         for p in group] for group in grouped])\n    assignment, lifts ='),
    ))

    def best(t, y, indices, prediction, cfg):
        costs.clear()
        result = traced_piece(t, y, indices, prediction, cfg)
        choices.append(dict(stage=stage, indices=indices.tolist(),
                            degree=None if result is None else result["degree"], costs=costs.copy()))
        return result

    def finish(*args, **kwargs):
        nonlocal stage
        stage = "finalization"
        return traced_finish(*args, **kwargs)

    with patch.object(graph, "finish_lane", finish), patch.object(poly, "_best_piece", best):
        result = graph.fit_lane(t, y, cfg)
    notes["assignment"] = result["assignment"].tolist()
    return notes, choices, distances


def polynomial_divergence(left, right, moves, cfg):
    def lanes(packet):
        return {row["observation_id"]: (row["receiver"], row["channel"], row["actual_rf_hz"])
                for row in packet["observations"]}

    location = lanes(left)
    receipts = []
    for lane in sorted({location[oid] for oid in moves}):
        runs, sorted_ids, sorted_times = [], [], []
        for source in (left, right):
            selection = [row for row in source["observations"] if location[row["observation_id"]] == lane]
            times = np.array([row["time_s"] for row in selection])
            values = np.array([row["measured_cfo_hz"] for row in selection])
            ordered, _, order, _ = graph.prepare_lane(times, values)
            sorted_ids.append([selection[i]["observation_id"] for i in order])
            sorted_times.append(ordered)
            runs.append(trace_polynomials(times, values, cfg))
        (original, a, left_distances), (candidate, b, right_distances) = runs
        changed = [i for i, (before, after) in enumerate(zip(
            original["arbitration"], candidate["arbitration"], strict=True,
        )) if before != after]
        first_owner = None
        if changed:
            first = changed[0]
            first_owner = dict(
                changed_count=len(changed), sorted_row=first,
                time_s=float(sorted_times[0][first]),
                owners=[original["arbitration"][first], candidate["arbitration"][first]],
                residuals_hz=[left_distances[first], right_distances[first]],
            )
        first = next((dict(call=index, original=x, candidate=y) for index, (x, y) in enumerate(zip(a, b))
                      if any(x[field] != y[field] for field in ("stage", "indices", "degree"))), None)
        if first:
            prior = {sorted_ids[0][i] for i in first["original"]["indices"]}
            next_support = {sorted_ids[1][i] for i in first["candidate"]["indices"]}
            first["accounts_for_final_moves"] = (prior ^ next_support
                                                 == {oid for oid in moves if location[oid] == lane})
        receipts.append(dict(
            lane=lane, polynomial_calls=[len(a), len(b)], first_choice_change=first,
            first_arbitration_change=first_owner,
            stages={key: original[key] == candidate[key] for key in original},
        ))
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("native", type=Path, nargs=3)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--audit-polynomial", action="store_true")
    args = parser.parse_args()
    if args.build:
        if args.library is None:
            parser.error("--build requires --library")
        build(args.library)
    if args.library is not None and not args.timing and not args.verify:
        parser.error("native tracing requires either --verify or --timing")
    pins = [path.read_bytes() for path in args.native]
    documents = [json.loads(raw) for raw in pins]
    ranks = [selection_ranks(doc) for doc in documents[:2]]
    if ranks[0] != ranks[1]:
        raise ValueError("The saved dense native inputs have different winning ranks")
    cfg = TrackConfig(**json.loads(args.config.read_bytes())["config"])
    results = []
    for raw, document in zip(pins, documents, strict=True):
        scope = (nullcontext({}) if args.library is None
                 else native_paths(args.library, verify=args.verify))
        with scope as counters:
            prepared, stats = run(document, cfg, trace=not args.timing)
        results.append((prepared, dict(stats, native_sha256=sha256(raw).hexdigest(),
                                      native_path_metrics=dict(counters))))
    left, right = results[:2]
    comparison = membership_difference(left[0], right[0])
    comparison["matched_opportunities"] = len(ranks[0])
    if args.audit_polynomial:
        comparison["polynomial"] = polynomial_divergence(
            left[0], right[0], comparison["membership_changes"], cfg,
        )
    if not args.timing:
        comparison["first_divergence"] = first_path_difference(left[1]["routes"], right[1]["routes"])
    print(json.dumps(dict(runs=[r[1] for r in results], dense_comparison=comparison),
                     default=_json_value, allow_nan=False))


if __name__ == "__main__":
    main()
