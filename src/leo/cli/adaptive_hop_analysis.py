"""Low-priority, bounded actual-visit metrics backfill; no radio or scheduling writes."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

from pydantic import TypeAdapter

from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisService
from leo.scanner.adaptive_hop import SessionId
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.analysis_worker_lock import analysis_worker_lock


def _visits(text: str) -> int:
    value = int(text)
    if not 1 <= value <= 2500:
        raise argparse.ArgumentTypeError("visit budget must be in 1..2500")
    return value


def _seconds(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or not 0 < value <= 1800:
        raise argparse.ArgumentTypeError("time budget must be in (0, 1800] seconds")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, required=True, help="Existing local recording root; never QNAP."
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--maximum-visits", type=_visits, default=2500)
    parser.add_argument(
        "--maximum-seconds",
        type=_seconds,
        default=300,
        help="Stop at a visit boundary; an in-flight visit finishes first.",
    )
    parser.add_argument(
        "--probe-stride-ms",
        type=int,
        choices=(10, 20, 40, 60, 120),
        default=10,
        help="Default dense 10 ms stride; alternatives create distinct analyses.",
    )
    args = parser.parse_args()
    try:
        TypeAdapter(SessionId).validate_python(args.session_id)
    except ValueError:
        parser.error("invalid adaptive session identifier")
    try:
        os.nice(10)
        with ExitStack() as resources:
            products = AdaptiveHopAnalysisStore(args.bulk_root)
            resources.callback(products.close)
            captures = AdaptiveHopIqStore(args.bulk_root, read_only=True)
            resources.callback(captures.close)
            # Use the existing public worker lease so fixed and adaptive desktop
            # analysis cannot compete. No fixed input/product is read or modified.
            with analysis_worker_lock(args.bulk_root) as acquired:
                if not acquired:
                    print(json.dumps({"state": "busy", "reason": "analysis worker is active"}))
                    return
                result = AdaptiveHopAnalysisService(
                    inputs=AdaptiveHopAnalysisInputStore(captures),
                    products=products,
                ).analyze_session(
                    args.session_id,
                    maximum_visits=args.maximum_visits,
                    maximum_seconds=args.maximum_seconds,
                    probe_stride_ms=args.probe_stride_ms,
                )
                print(json.dumps(asdict(result), sort_keys=True))
    except Exception as error:
        print(
            json.dumps(
                {"state": "failed", "error_type": type(error).__name__, "message": str(error)[:512]}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
