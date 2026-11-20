"""Rebuild complementary Graphs from held-block-free native winners."""

import json
import sys
from resource import RLIMIT_AS, setrlimit
from unittest.mock import patch

from tools.pipeline_eval.variants import native_lean as native


def worker(request):
    limit = native.AS_LIMIT_MIB * 1024**2
    setrlimit(RLIMIT_AS, (limit, limit))
    from tools.pipeline_eval.qualification import native_clock_model_worker as frontend
    from tools.pipeline_eval.variants import joint_clock_model as smooth
    from tools.pipeline_eval.variants import outside_predictive as variant

    lanes = {}
    original_extract, original_infer = native.peak_lanes, smooth.infer
    receipt = {}

    def collect(*args):
        clock, winners, counts = original_extract(*args)
        lanes.update(winners)
        return clock, winners, counts

    def infer(document, offer, catalogue, *, clock=True):
        time = native._now()
        initial = original_infer(document, offer, catalogue, clock=clock)
        receipt["initial"] = initial
        receipt["initial_time"] = native._elapsed(time)
        config = json.loads(native._load(request["track_config"], native.BLOCK_BYTES))["config"]
        halo = dict(offer, id=offer["id"] + "-training", width_km=variant.HALO_KM)
        xy = variant.nodes(offer["width_km"] / 2)
        folds, meta = [], []
        original_refine = smooth.refine
        for split in (0, 1):
            unfold = native._now()
            train, held = variant.partition(lanes, split)
            tracks = native.graph_projection(train, config)
            training = dict(document, tracks=tracks)
            captured = {}

            def retain(rows, start, tile, region, half, arm, *, clock, captured=captured):
                result = original_refine(rows, start, tile, region, half, arm, clock=clock)
                captured[arm] = rows, tile, region, result[0].state
                return result

            with patch.object(smooth, "refine", retain):
                fitted = original_infer(training, halo, catalogue, clock=clock)
            # Before both final paired positions are available, a capture may contain
            # provisional validation fits. They do not establish the fixed assignments.
            complete = all(a.get("forced_latlon") is not None for a in fitted["arms"].values())
            prep = native._elapsed(unfold)
            held_time = native._now()
            votes = (
                {
                    arm: variant.held_forecast(*context, held, xy)
                    for arm, context in captured.items()
                }
                if complete
                else {}
            )
            folds.append(votes)
            meta.append(
                dict(
                    train_graph_sha256=native.projection_digest(training),
                    train_peaks=sum(map(len, train.values())),
                    held_raw_peaks=sum(map(len, held.values())),
                    train_arms=fitted["arms"],
                    train_status=fitted["status"],
                    train_reason=fitted["reason"],
                    training_time=prep,
                    held_time=native._elapsed(held_time),
                )
            )
        decision = variant.verdict(folds)
        receipt.update(folds=folds, fold_receipts=meta, outside_decision=decision)
        return variant.apply(initial, decision)

    with patch.object(native, "peak_lanes", collect), patch.object(smooth, "infer", infer):
        output = frontend.worker(request)
    output["result"]["boundary"] = variant.BOUNDARY
    return output | receipt


if __name__ == "__main__":
    start = native._now()
    output = worker(json.load(sys.stdin))
    output["worker"] = native._elapsed(start)
    json.dump(output, sys.stdout, allow_nan=False, sort_keys=True)
