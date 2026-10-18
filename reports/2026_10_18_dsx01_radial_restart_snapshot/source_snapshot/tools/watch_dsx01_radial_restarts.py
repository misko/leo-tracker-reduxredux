"""Refresh post-fit restart plots until the matching full campaign terminates.

This process never imports or invokes the numerical campaign orchestrator and
does not alter inference sources or results. A pilot receipt is not completion
of a larger campaign, even when its source fingerprint is identical.
"""

import argparse
import json
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from report_dsx01_radial_restarts import OUTPUT, run


def matching_receipt(output, expected_jobs=None):
    output = Path(output)
    protocol = json.loads((output / "protocol.json").read_text())
    requested = (
        protocol["expected_pipeline_results"]
        + len(protocol["cases"]) * len(protocol["starts"])
    )
    if expected_jobs is not None and requested != expected_jobs:
        raise ValueError("protocol job count differs from the requested watcher campaign")
    receipt_path = output / "run_receipt.json"
    if not receipt_path.exists():
        return requested, None
    try:
        receipt = json.loads(receipt_path.read_text())
    except json.JSONDecodeError:
        # The orchestrator writes its terminal receipt only once, but readers
        # can catch the brief interval before that write has completed.
        return requested, None
    if (
        receipt.get("source_fingerprint") != protocol["source_fingerprint"]
        or receipt.get("requested") != requested
    ):
        return requested, None
    return requested, receipt


def receipt_exit_code(receipt):
    if receipt is None:
        return None
    if (
        receipt.get("failures")
        or receipt.get("blocked_by_dependency")
        or receipt.get("completed") != receipt.get("requested")
    ):
        return 1
    return 0


def watch(output=OUTPUT, *, interval_seconds=120, expected_jobs=None, sleep=time.sleep, report=run):
    if interval_seconds <= 0:
        raise ValueError("positive watcher interval required")
    output = Path(output)
    cycles = 0
    while True:
        requested, receipt = matching_receipt(output, expected_jobs)
        error = None
        audit = {}
        try:
            audit = report(output)
        except Exception:
            error = traceback.format_exc()
        cycles += 1
        code = receipt_exit_code(receipt)
        status = dict(
            updated_utc=datetime.now(UTC).isoformat(),
            expected_campaign_jobs=requested,
            refresh_cycles=cycles,
            terminal_matching_receipt=receipt is not None,
            exit_code=2 if code is not None and error else code,
            report_error=error,
            completed_pipeline_results=audit.get("completed_worker_results"),
            finite_arm_endpoints=audit.get("finite_arm_endpoints"),
            groups_redrawn=audit.get("groups_redrawn"),
            interval_seconds=interval_seconds,
        )
        temporary = output / "watcher_status.tmp"
        temporary.write_text(json.dumps(status, indent=2) + "\n")
        temporary.replace(output / "watcher_status.json")
        print(json.dumps(status), flush=True)
        if code is not None:
            return 2 if error else code
        sleep(interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--interval-seconds", type=float, default=120)
    parser.add_argument("--expected-jobs", type=int)
    args = parser.parse_args()
    raise SystemExit(watch(
        args.output,
        interval_seconds=args.interval_seconds,
        expected_jobs=args.expected_jobs,
    ))
