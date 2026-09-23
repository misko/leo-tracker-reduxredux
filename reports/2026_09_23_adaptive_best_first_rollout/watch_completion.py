#!/usr/bin/env python3
"""Read-only completion watcher for one frozen adaptive-position V2 rollout.

The watcher performs store/source-manifest audits without HTTP while work is in
progress.  When the frozen inventory has no pending publication it performs
one complete immutable-store plus served-API audit, then invokes the supplied
descriptive summary script.  It never starts workers, changes a queue, or
writes under the bulk store.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_receipt(path: Path) -> dict[str, Any]:
    receipt = json.loads(path.read_text())
    summary = receipt.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"audit receipt lacks a summary: {path}")
    states = summary.get("publication_states")
    if not isinstance(states, dict) or not isinstance(states.get("pending"), int):
        raise ValueError(f"audit receipt lacks pending state count: {path}")
    if not isinstance(summary.get("invalid_publication_count"), int):
        raise ValueError(f"audit receipt lacks invalid publication count: {path}")
    return receipt


def _audit_command(args: argparse.Namespace, output: Path, *, api: bool) -> list[str]:
    command = [
        str(args.python),
        str(args.auditor),
        "--bulk-root",
        str(args.bulk_root),
        "--inventory",
        str(args.inventory),
        "--version",
        "2",
        "--output",
        str(output),
    ]
    if api:
        command.extend(("--api-base", args.api_base, "--require-complete"))
    return command


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _failure(
    args: argparse.Namespace,
    *,
    reason: str,
    receipt: Path | None,
    completed: subprocess.CompletedProcess[str] | None,
) -> int:
    _write_new(
        args.failure_receipt,
        {
            "schema": "adaptive-tle-position-v2-completion-watcher/v1",
            "finished_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "outcome": "invalid-or-command-failure",
            "reason": reason,
            "audit_receipt": str(receipt) if receipt is not None else None,
            "audit_returncode": completed.returncode if completed is not None else None,
            "audit_stdout": completed.stdout if completed is not None else None,
            "audit_stderr": completed.stderr if completed is not None else None,
            "read_only": True,
        },
    )
    return 2


def watch(args: argparse.Namespace) -> int:
    polls = 0
    while True:
        polls += 1
        receipt_path = args.receipt_dir / f"store-{_utc_stamp()}-{polls:04d}.json"
        completed = _run(_audit_command(args, receipt_path, api=False))
        if not receipt_path.exists():
            return _failure(
                args,
                reason="store audit exited without a receipt",
                receipt=None,
                completed=completed,
            )
        receipt = _read_receipt(receipt_path)
        summary = receipt["summary"]
        progress = {
            "schema": "adaptive-tle-position-v2-completion-watcher/v1",
            "polled_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "poll_number": polls,
            "store_audit_receipt": str(receipt_path),
            "store_audit_summary": summary,
            "read_only": True,
        }
        _write_new(args.receipt_dir / f"progress-{_utc_stamp()}-{polls:04d}.json", progress)
        if completed.returncode or summary["invalid_publication_count"]:
            return _failure(
                args,
                reason="store audit reported invalid publication or command failure",
                receipt=receipt_path,
                completed=completed,
            )
        if summary["publication_states"]["pending"] == 0:
            break
        if args.max_polls is not None and polls >= args.max_polls:
            return 0
        time.sleep(args.poll_seconds)

    final = _run(_audit_command(args, args.final_audit, api=True))
    if final.returncode or not args.final_audit.exists():
        return _failure(
            args,
            reason="complete store/API audit failed",
            receipt=args.final_audit if args.final_audit.exists() else None,
            completed=final,
        )
    final_receipt = _read_receipt(args.final_audit)
    final_summary = final_receipt["summary"]
    if final_summary["publication_states"]["pending"] or final_summary["invalid_publication_count"]:
        return _failure(
            args,
            reason="complete store/API audit was not complete and valid",
            receipt=args.final_audit,
            completed=final,
        )
    summary_command = [
        str(args.python),
        str(args.summarizer),
        "--bulk-root",
        str(args.bulk_root),
        "--inventory",
        str(args.inventory),
        "--version",
        "v2",
        "--output",
        str(args.summary_output),
    ]
    summary_run = _run(summary_command)
    if summary_run.returncode:
        return _failure(
            args,
            reason="descriptive summary failed after a valid complete audit",
            receipt=args.final_audit,
            completed=summary_run,
        )
    _write_new(
        args.completion_receipt,
        {
            "schema": "adaptive-tle-position-v2-completion-watcher/v1",
            "finished_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "outcome": "complete",
            "final_audit": str(args.final_audit),
            "summary_output": str(args.summary_output),
            "summary_stdout": summary_run.stdout,
            "summary_stderr": summary_run.stderr,
            "read_only": True,
        },
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="qualified release interpreter")
    parser.add_argument("--auditor", type=Path, required=True)
    parser.add_argument("--summarizer", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--final-audit", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--completion-receipt", type=Path, required=True)
    parser.add_argument("--failure-receipt", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=180.0)
    parser.add_argument(
        "--max-polls", type=int, help="bounded test-only stop after this many polls"
    )
    args = parser.parse_args()
    if args.poll_seconds < 0:
        parser.error("--poll-seconds must be non-negative")
    if args.max_polls is not None and args.max_polls < 1:
        parser.error("--max-polls must be positive")
    sys.exit(watch(args))


if __name__ == "__main__":
    main()
