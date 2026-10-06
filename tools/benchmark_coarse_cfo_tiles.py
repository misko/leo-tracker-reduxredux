"""Bounded, read-only saved-visit parity/timing comparison for CFO tiling."""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

from leo.analysis.starlink import acquisition
from leo.scanner.adaptive_hop_analysis import (
    VariableDwellAnalysisConfigurationV5,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-acquisition", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session", action="append", required=True)
    parser.add_argument("--visits", default="0,71,203,503,901,1201,1701,2101")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    indexes = tuple(int(value) for value in args.visits.split(","))
    if len(args.session) * len(indexes) > 48:
        parser.error("benchmark is bounded to 48 saved visits")
    spec = importlib.util.spec_from_file_location("coarse_baseline", args.baseline_acquisition)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    baseline = module._folded_anchor_score_grid_native
    candidate = acquisition._folded_anchor_score_grid_native
    rows = []
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        inputs = AdaptiveHopAnalysisInputStore(store)
        for sid in args.session:
            with inputs.source(sid) as source:
                configuration = VariableDwellAnalysisConfigurationV5(
                    sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                    receiver_ids=source.receipt.plan.geometry.receiver_ids,
                    probe_stride_ms=120,
                )
                for index in indexes:
                    row = {
                        "session": sid,
                        "visit": index,
                        "rate": source.receipt.plan.geometry.sample_rate_hz,
                    }
                    products = {}
                    order = (
                        ("baseline", "candidate")
                        if len(rows) % 2 == 0
                        else ("candidate", "baseline")
                    )
                    for variant in order:
                        acquisition._folded_anchor_score_grid_native = (
                            baseline if variant == "baseline" else candidate
                        )
                        cpu, wall = time.process_time(), time.perf_counter()
                        result = analyze_adaptive_hop_visit(
                            source, index, configuration=configuration
                        )
                        row[variant] = {
                            "cpu_s": time.process_time() - cpu,
                            "wall_s": time.perf_counter() - wall,
                        }
                        products[variant] = result.model_dump(mode="json")
                    row["exact_parity"] = products["baseline"] == products["candidate"]
                    row["probe_count"] = len(products["candidate"]["probes"])
                    row["candidate_count"] = sum(
                        p["candidate_count"] for p in products["candidate"]["probes"]
                    )
                    rows.append(row)
                    args.output.write_text(json.dumps(rows, indent=2) + "\n")
                    print(json.dumps(row), flush=True)
                    if not row["exact_parity"]:
                        raise RuntimeError("scientific output mismatch")
    finally:
        acquisition._folded_anchor_score_grid_native = candidate
        store.close()


if __name__ == "__main__":
    main()
