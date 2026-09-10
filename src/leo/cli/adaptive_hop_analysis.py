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
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.presentation.adaptive_hop_analysis import render_adaptive_hop_overview
from leo.scanner.adaptive_hop import SessionId
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
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


def next_pending(captures, presentation, *, probe_stride_ms: int) -> str | None:
    """Resume saved work before older unstarted captures; never read IQ to select.

    Finish metrics-only jobs first. Oldest creation time breaks ties, preventing
    a newly arriving capture from repeatedly preempting an unfinished one.
    """
    selected = None
    for capture in captures.iter_sessions():
        status = presentation.status(capture.session_id, probe_stride_ms=probe_stride_ms)
        if status is None:
            raise ValueError("published adaptive capture disappeared during selection")
        if status.state == "figures_ready":
            continue
        priority = {"metrics_complete": 0, "partial": 1, "not_started": 2}[status.state]
        candidate = (priority, capture.manifest.created_utc_ns, capture.session_id)
        if selected is None or candidate < selected:
            selected = candidate
    return selected[2] if selected is not None else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, required=True, help="Existing local recording root; never QNAP."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--session-id")
    selection.add_argument(
        "--pending", action="store_true", help="Resume one pending published capture, then return."
    )
    parser.add_argument("--maximum-workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--maximum-visits", type=_visits, default=2500)
    parser.add_argument(
        "--maximum-seconds",
        type=_seconds,
        default=300,
        help=(
            "Metrics budget checked at batch boundaries; "
            "at most two in-flight visits finish first. "
            "Overview rendering follows completion and is outside this budget."
        ),
    )
    parser.add_argument(
        "--probe-stride-ms",
        type=int,
        choices=(10, 20, 40, 60, 120),
        default=10,
        help="Default dense 10 ms stride; alternatives create distinct analyses.",
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Do not render the overview after metrics complete; metrics stay resumable.",
    )
    args = parser.parse_args()
    try:
        if args.session_id is not None:
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
                session_id = args.session_id
                if args.pending:
                    session_id = next_pending(
                        captures,
                        AdaptiveHopAnalysisPresentationStore(args.bulk_root),
                        probe_stride_ms=args.probe_stride_ms,
                    )
                    if session_id is None:
                        print(
                            json.dumps(
                                {
                                    "state": "idle",
                                    "reason": "all published adaptive figures are ready",
                                }
                            )
                        )
                        return
                result = AdaptiveHopAnalysisService(
                    inputs=AdaptiveHopAnalysisInputStore(captures),
                    products=products,
                ).analyze_session(
                    session_id,
                    maximum_visits=args.maximum_visits,
                    maximum_seconds=args.maximum_seconds,
                    probe_stride_ms=args.probe_stride_ms,
                    maximum_workers=args.maximum_workers,
                )
                payload = {**asdict(result), "overview_state": "not_ready"}
                if result.state == "metrics_complete" and not args.metrics_only:
                    overview = AdaptiveHopOverviewService(
                        inputs=AdaptiveHopAnalysisInputStore(captures),
                        products=products,
                        renderer=render_adaptive_hop_overview,
                    ).render_session(session_id, probe_stride_ms=args.probe_stride_ms)
                    payload["overview_state"] = "ready"
                    payload["overview_metrics_manifest_sha256"] = overview.metrics_manifest_sha256
                print(json.dumps(payload, sort_keys=True))
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
