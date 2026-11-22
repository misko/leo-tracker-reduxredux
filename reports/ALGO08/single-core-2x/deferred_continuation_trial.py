"""Replay a verified pre-continuation ledger while charging every queried native call."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.deferred_continuation import DeferredContinuation


def compare(path, detection_path, capacity):
    ledger_bytes = path.read_bytes()
    ledger = json.loads(gzip.decompress(ledger_bytes))
    reference = json.loads(detection_path.read_bytes())["source"]
    if ledger["raw_authority"] != reference["raw_recording_authority_digest"]:
        raise ValueError("Ledger and detector publication refer to different samples")
    rows, costs = ledger["rows"], ledger["native_cpu_ns"]
    if not len(rows) == len(costs) == len(reference["probes"]):
        raise ValueError("Incomplete factor ledger")
    probe_metadata = [{k: v for k, v in row.items() if k != "candidates"} for row in rows]
    stock = Continuation()
    normal = []
    start = process_time()
    for row in rows:
        _, index, _ = stock.select(row)
        normal.append([] if index is None else [row["candidates"][index]])
    normal_cpu = process_time() - start
    selected = []
    queried = set()
    planner = DeferredContinuation(capacity)
    def measure(index):
        if index in queried:
            raise ValueError("Native measurement charged twice")
        queried.add(index)
        return rows[index]["candidates"]
    start = process_time()
    for index, probe in enumerate(probe_metadata):
        selected.append(planner.select(probe, lambda i=index: measure(i)))
    proposed_cpu = process_time() - start
    if selected != normal or any(dict(probe, candidates=output) != published
                                 for probe, output, published in zip(probe_metadata, selected,
                                                                    reference["probes"], strict=True)):
        raise ValueError("Deferred measurement changed a published selection")
    skipped = set(range(len(rows))) - queried
    total_cpu = sum(costs) / 1e9
    saved_cpu = sum(costs[i] for i in skipped) / 1e9
    published_cpu = sum(cost for cost, result in zip(costs, selected, strict=True) if result) / 1e9
    return dict(ledger_sha256=sha256(ledger_bytes).hexdigest(), detector_sha256=ledger["detector_sha256"],
                raw_authority=ledger["raw_authority"], pending_budget=capacity, rows=len(rows),
                selections=sum(bool(result) for result in selected),
                unqueried_lanes=len(skipped), unqueried_verified_factors=sum(len(rows[i]["candidates"]) for i in skipped),
                total_native_cpu_s=total_cpu, unqueried_native_cpu_s=saved_cpu,
                native_cpu_s_on_published_lanes=published_cpu,
                native_cpu_s_on_unpublished_lanes=total_cpu - published_cpu,
                unqueried_fraction_of_native_cpu=saved_cpu / total_cpu, stock_continuation_cpu_s=normal_cpu,
                planner_cpu_s=proposed_cpu, estimated_net_cpu_s=saved_cpu - (proposed_cpu - normal_cpu),
                counters=dict(planner.counts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=3, action="append", required=True, metavar=("NAME", "LEDGER", "DETECTIONS"))
    parser.add_argument("--pending", type=int, default=16)
    args = parser.parse_args()
    print(json.dumps({name: compare(Path(path), Path(detection), args.pending)
                      for name, path, detection in args.case}, indent=2))
