"""Explain no-trajectory outcomes using existing GLRT candidates and gap limits."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def gap_runs(times):
    runs = []
    run = []
    for time_ns in sorted(times):
        if run and time_ns - run[-1] > 4_000_000_000:
            runs.append(run)
            run = []
        run.append(time_ns)
    if run:
        runs.append(run)
    return [{"observations": len(r), "span_s": (r[-1] - r[0]) / 1e9} for r in runs]


def inspect(audit_dir, bulk_root):
    output = []
    store = ScannerTrackingInputStore(bulk_root)
    try:
        for path in sorted(audit_dir.glob("scan-*.json")):
            row = json.loads(path.read_text())
            product = row["tracking"].get("product") or {}
            if row["tracking"]["state"] != "complete" or product.get("tracklets"):
                continue
            candidates = project_scanner_candidates(store.load(row["session_id"]))
            lanes = defaultdict(dict)
            for candidate in candidates:
                lanes[f"CH{candidate.channel}{candidate.edge.value}"][candidate.source_group_id] = (
                    candidate.support_center_utc_ns
                )
            output.append(
                {
                    "session_id": row["session_id"],
                    "actual_projected_candidates": len(candidates),
                    "published_projected_candidates": product["projected_candidate_count"],
                    "lanes": [
                        {
                            "lane": lane,
                            "distinct_observations": len(points),
                            "runs": gap_runs(points.values()),
                        }
                        for lane, points in lanes.items()
                    ],
                }
            )
    finally:
        store.close()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inspect(args.audit_dir, args.bulk_root), indent=2) + "\n")
