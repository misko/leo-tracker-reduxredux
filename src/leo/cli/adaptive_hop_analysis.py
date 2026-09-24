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

from leo.application.adaptive_hop_analysis import (
    AdaptiveHopAnalysisService,
    HostAdaptiveAnalysisService,
)
from leo.application.adaptive_hop_overview import AdaptiveHopOverviewService
from leo.presentation.adaptive_hop_analysis import (
    render_adaptive_hop_overview,
    render_host_adaptive_hop_overview,
)
from leo.scanner.adaptive_hop import SessionId
from leo.scanner.host_adaptive import HostAdaptiveHopReceiptV2
from leo.scanner.host_adaptive_products import (
    HostAdaptiveAnalysisBindingV2,
    HostAdaptiveAnalysisBindingV3,
    HostAdaptiveMetricsManifestV2,
    HostAdaptiveMetricsManifestV3,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore


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
    """Resume saved work, then keep native 10M captures current; never read IQ.

    Finish metrics-only and partial jobs first. A newly published native capture
    precedes the historical legacy backlog so its complete overview and tracking
    products can be published before the next ten-minute acquisition. Legacy
    work retains oldest-first ordering.
    """
    selected = None
    for capture in captures.iter_sessions():
        status = presentation.status_for_capture(capture, probe_stride_ms=probe_stride_ms)
        if status is None:
            raise ValueError("published adaptive capture disappeared during selection")
        if status.state == "figures_ready":
            continue
        host_native = isinstance(
            getattr(capture.manifest, "receipt", None), HostAdaptiveHopReceiptV2
        )
        priority = {
            "metrics_complete": 0,
            "partial": 1,
            "not_started": 2 if host_native else 3,
        }[status.state]
        creation_order = (
            -capture.manifest.created_utc_ns
            if host_native and status.state == "not_started"
            else capture.manifest.created_utc_ns
        )
        candidate = (priority, creation_order, capture.session_id)
        if selected is None or candidate < selected:
            selected = candidate
    return selected[2] if selected is not None else None


def pending_sessions(
    captures, presentation, *, probe_stride_ms: int, limit: int
) -> tuple[str, ...]:
    """Choose newest pending sessions; spare capacity continuously drains backlog."""
    if limit < 1:
        raise ValueError("pending session limit must be positive")
    selected = []
    for _, session_id in captures.publication_index():
        capture = captures.inspect(session_id)
        status = presentation.status_for_capture(capture, probe_stride_ms=probe_stride_ms)
        if status.state != "figures_ready":
            selected.append(session_id)
        if len(selected) == limit:
            break
    return tuple(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument(
        "--bulk-root",
        type=Path,
        help="Legacy combined capture and product root.",
    )
    roots.add_argument(
        "--capture-root",
        type=Path,
        help="Existing read-only capture root, including /srv/bulk or QNAP.",
    )
    parser.add_argument(
        "--metrics-root",
        type=Path,
        help="Writable analysis root; required with --capture-root.",
    )
    parser.add_argument(
        "--tracking-root",
        type=Path,
        help="Writable phase/tracking root; defaults to --metrics-root.",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--session-id")
    selection.add_argument(
        "--pending", action="store_true", help="Resume one pending published capture, then return."
    )
    parser.add_argument("--maximum-workers", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--host-maximum-workers",
        type=int,
        choices=(1, 2, 3, 4),
        default=4,
        help="Worker bound for native-10M single-RX captures; legacy jobs keep their own bound.",
    )
    parser.add_argument("--maximum-visits", type=_visits, default=2500)
    parser.add_argument(
        "--maximum-seconds",
        type=_seconds,
        default=300,
        help=(
            "Metrics budget checked at batch boundaries; "
            "in-flight visits finish first (two legacy or four native single-RX). "
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
    if args.capture_root is not None and args.metrics_root is None:
        parser.error("--capture-root requires a separate --metrics-root")
    capture_root = args.capture_root if args.capture_root is not None else args.bulk_root
    metrics_root = args.metrics_root if args.metrics_root is not None else args.bulk_root
    tracking_root = args.tracking_root if args.tracking_root is not None else metrics_root
    assert capture_root is not None and metrics_root is not None and tracking_root is not None
    if args.capture_root is not None:
        capture = capture_root.resolve()
        for label, output in (("metrics", metrics_root), ("tracking", tracking_root)):
            resolved = output.resolve()
            protected = (capture, Path("/srv/bulk"), Path("/mnt/qnap01"))
            if any(root == resolved or root in resolved.parents for root in protected):
                parser.error(
                    f"--{label}-root must be report-local and outside read-only capture storage"
                )
    try:
        if args.session_id is not None:
            TypeAdapter(SessionId).validate_python(args.session_id)
    except ValueError:
        parser.error("invalid adaptive session identifier")
    try:
        os.nice(10)
        with ExitStack() as resources:
            products = AdaptiveHopAnalysisStore(metrics_root)
            resources.callback(products.close)
            captures = AdaptiveHopIqStore(capture_root, read_only=True)
            resources.callback(captures.close)
            session_id = args.session_id
            if args.pending:
                session_id = next_pending(
                    captures,
                    AdaptiveHopAnalysisPresentationStore(
                        capture_root,
                        analysis_root=metrics_root,
                        tracking_root=tracking_root,
                    ),
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
            host = isinstance(
                captures.inspect(session_id).manifest.receipt, HostAdaptiveHopReceiptV2
            )
            service = HostAdaptiveAnalysisService if host else AdaptiveHopAnalysisService
            try:
                result = service(
                    inputs=AdaptiveHopAnalysisInputStore(captures),
                    products=products,
                ).analyze_session(
                    session_id,
                    maximum_visits=args.maximum_visits,
                    maximum_seconds=args.maximum_seconds,
                    probe_stride_ms=args.probe_stride_ms,
                    maximum_workers=args.host_maximum_workers if host else args.maximum_workers,
                )
            except BlockingIOError:
                print(json.dumps({"state": "busy", "session_id": session_id}))
                return
            payload = {**asdict(result), "overview_state": "not_ready"}
            if result.state == "metrics_complete" and not args.metrics_only:
                overview = AdaptiveHopOverviewService(
                    inputs=AdaptiveHopAnalysisInputStore(captures),
                    products=products,
                    renderer=_render_overview,
                ).render_session(session_id, probe_stride_ms=args.probe_stride_ms)
                payload["overview_state"] = "ready"
                payload["overview_metrics_manifest_sha256"] = overview.metrics_manifest_sha256
                from leo.cli.adaptive_relative_phase import run as run_relative_phase

                try:
                    relative_phase = run_relative_phase(
                        capture_root,
                        session_id,
                        analysis_root=metrics_root,
                        output_root=tracking_root,
                        probe_stride_ms=args.probe_stride_ms,
                        maximum_seconds=120,
                    )
                except BlockingIOError:
                    relative_phase = {"state": "partial"}
                payload["relative_phase_state"] = relative_phase["state"]
                if relative_phase["state"] != "complete":
                    payload["state"] = "partial"
            phase = AdaptiveHopAnalysisPresentationStore(
                capture_root,
                analysis_root=metrics_root,
                tracking_root=tracking_root,
            ).phase_status(session_id, probe_stride_ms=args.probe_stride_ms)
            payload["dual_rx_phase_state"] = None if phase is None else phase.state
            print(json.dumps(payload, sort_keys=True))
    except Exception as error:
        print(
            json.dumps(
                {"state": "failed", "error_type": type(error).__name__, "message": str(error)[:512]}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error


def _render_overview(binding, metrics, visits):
    if isinstance(binding, HostAdaptiveAnalysisBindingV3):
        metrics = HostAdaptiveMetricsManifestV3.model_validate(metrics.model_dump())
        return render_host_adaptive_hop_overview(binding, metrics, visits)
    if isinstance(binding, HostAdaptiveAnalysisBindingV2):
        metrics = HostAdaptiveMetricsManifestV2.model_validate(metrics.model_dump())
        return render_host_adaptive_hop_overview(binding, metrics, visits)
    return render_adaptive_hop_overview(binding, metrics, visits)


if __name__ == "__main__":
    main()
