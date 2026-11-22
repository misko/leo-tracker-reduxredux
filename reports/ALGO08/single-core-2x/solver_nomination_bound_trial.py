"""Compare a frozen subset witness on one saved zero-state nomination anchor."""

import argparse
import json
from collections import Counter
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np
from solver_streamed_nomination_trial import receipt

from leo.analysis.localization_v3 import discovery
from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from tools import algo08_position
from tools.pipeline_eval.variants import algo08_causal_reuse, v5_core
from tools.pipeline_eval.variants.algo08_nomination_bound import full_profiles, subset_nomination
from tools.pipeline_eval.variants.algo08_streamed_nomination import white_nomination


def dense(y, forecast, visible, white, metrics):
    j, costs, aliases, bias, rms, innovations = white_nomination(y, forecast, visible, white)
    metrics["full_candidates"] += len(forecast)
    metrics["full_profile_cells"] += forecast.size
    return j, costs[j], aliases[j], bias, rms, innovations


def visible_only(y, forecast, visible, white, metrics):
    indexes = np.flatnonzero(visible)
    if not len(indexes):
        return dense(y, forecast, visible, white, metrics)
    (j, costs, aliases, bias, rms, innovations), _ = full_profiles(
        y, forecast, visible, white, indexes, check_alias=False,
    )
    metrics["full_candidates"] += len(indexes)
    metrics["full_profile_cells"] += len(indexes) * len(y)
    return indexes[j], costs[j], aliases[j], bias, rms, innovations


def run_scan(scan, keys):
    tracks = [i for i in scan.curved if keys is None or scan.tracks[i]["key"] in keys]
    if not tracks or (keys is not None and len(tracks) != len(keys)):
        raise ValueError("Expected the declared original curved components")
    start = process_time_ns()
    f, e, _ = discovery.phase_linear_frequency(scan.geometry, *scan.search_region.latlon((0., 0.)))
    projection = process_time_ns() - start
    start = process_time_ns()
    inputs = []
    for i in tracks:
        track, cols = scan.tracks[i], scan.index[i]
        inputs.append((track["values"], track["rf_hz"] / discovery.REFERENCE_RF * f[:, cols],
                       e[:, cols].min(axis=1) >= 0, scan.white[i]))
    preparation = process_time_ns() - start
    methods = {"full": dense, "visible_only": visible_only, "bound": subset_nomination}
    results = {}
    order = ["full", "visible_only", "bound"]
    for modes in (order, order[::-1], order):
        for mode in modes:
            metrics = Counter()
            start = process_time_ns()
            rows = [methods[mode](*data, metrics) for data in inputs]
            elapsed = process_time_ns() - start
            if mode not in results:
                results[mode] = dict(ns=[], metrics=dict(metrics), rows=rows)
            else:
                prior = results[mode]
                same_order = zip(rows, prior["rows"], strict=True)
                if any(signature(a) != signature(b) for a, b in same_order):
                    raise ValueError("Nomination changed across timed repeats")
            results[mode]["ns"].append(elapsed)

    stock = results["full"]["rows"]
    comparison = {}
    for mode, evidence in results.items():
        ok, float_changes, label_changes, max_score = 0, [], [], 0.
        for i, left, right in zip(tracks, stock, evidence.pop("rows"), strict=True):
            key = scan.tracks[i]["key"]
            if signature(left) == signature(right):
                ok += 1
            else:
                float_changes.append(key)
            if (left[0], left[2]) != (right[0], right[2]):
                label_changes.append(key)
            max_score = max(max_score, abs(left[1] - right[1]))
        comparison[mode] = dict(evidence, exact_rows=ok, differing_rows=float_changes,
                                changed_label_or_alias=label_changes, maximum_cost_delta=max_score)
    return dict(
        tracks=len(tracks), catalogue=len(scan.norads), shared_projection_ns=projection,
        shared_preparation_ns=preparation, visible_candidates=sum(int(x[2].sum()) for x in inputs),
        observations=sum(len(x[0]) for x in inputs), comparison=comparison,
    )


def signature(row):
    return int(row[0]), tuple(np.asarray(x).tobytes() for x in row[1:])


def run(native, archive, assets, region, keys):
    report = {}
    prepare = partial(
        algo08_causal_reuse.prepare, algo08_position.prepare_native_scan, statistics={},
    )

    def infer(prepared, search, bound, stages, **options):
        if prepared["status"] != "inputs_prepared":
            raise ValueError(prepared["status"])
        noise = sha256((json.dumps(prepared["noise"], sort_keys=True) + "\n").encode()).hexdigest()
        scan = v5_core.scan_context(prepared, search, noise, bound, "previous")
        report.update(run_scan(scan, keys))
        return dict(status="nomination_bound_trial_complete")

    with (
        patch.object(algo08_position, "prepare_native_scan", prepare),
        patch.object(v5_core, "infer", infer),
    ):
        _, _, report["orbit_policy"] = algo08_position.solve(native, archive, assets, region)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--stock", type=Path)
    parser.add_argument("--moments", type=Path)
    args = parser.parse_args()
    raw = args.native.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    keys = None
    if bool(args.stock) != bool(args.moments):
        parser.error("Provide both saved nomination rosters")
    if args.stock:
        stock, moments = receipt(args.stock, digest), receipt(args.moments, digest)
        keys = {key for key in stock if stock[key] != moments[key]}
        if len(keys) != 12:
            raise ValueError("Expected the 12 prerecorded nomination disagreements")
    region = Algo08Region.parse(json.loads(args.region.read_bytes()))
    scored = run(json.loads(raw), TleArchiveReader(args.archive), args.assets, region, keys)
    print(json.dumps(dict(scored, native_sha256=digest, region=region.document()),
                     default=_json_value, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
