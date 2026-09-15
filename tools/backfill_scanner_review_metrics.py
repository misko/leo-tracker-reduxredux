"""Bounded existing-IQ backfill into a separate research analysis store."""

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from leo.application.adaptive_hop_analysis import HostAdaptiveAnalysisService
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def run(sid, output):
    captures = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    products = AdaptiveHopAnalysisStore(output)
    try:
        receipt = captures.inspect(sid).manifest.receipt
        if (
            receipt.radio_serial != "104000bac4950008230026001b440a003a"
            or receipt.plan.geometry.receiver_ids != (0,)
            or receipt.plan.geometry.sample_rate_hz != 10_000_000
        ):
            raise ValueError("unexpected capture source")
        result = HostAdaptiveAnalysisService(
            inputs=AdaptiveHopAnalysisInputStore(captures), products=products
        ).analyze_session(
            sid,
            maximum_visits=2500,
            maximum_seconds=1800,
            probe_stride_ms=120,
            maximum_workers=2,
        )
        return asdict(result)
    finally:
        captures.close()
        products.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if (
        output == Path("/mnt/qnap01")
        or Path("/mnt/qnap01") in output.parents
        or output == Path("/srv/bulk/leo")
    ):
        parser.error("output must be a separate research store outside QNAP")
    output.mkdir(parents=True, exist_ok=True)
    os.nice(10)

    rows = [json.loads(p.read_text()) for p in sorted(args.reviews.glob("scan-hop-*.json"))]
    ids = [
        r["session_id"]
        for r in rows
        if r.get("error", "").startswith("BundleNotFoundError: adaptive analysis")
    ]
    if len(ids) > 6:
        raise ValueError("review backfill is bounded to six recordings")
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(run, sid, args.output) for sid in ids]
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)


if __name__ == "__main__":
    main()
