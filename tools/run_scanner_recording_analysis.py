#!/usr/bin/env python3
"""Run the current scanner Standard analysis on selected persisted IQ bundles."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from leo.cli.scanner import STANDARD_SCANNER_ANALYSIS_ID
from leo.presentation.scanner_analysis import (
    render_scanner_glrt64_response_png,
    render_scanner_pilot_carrier_tracking_png,
    render_scanner_pilot_doppler_png,
    render_scanner_pilot_segment_rates_png,
    render_scanner_waterfall_png,
)
from leo.scanner import analyze_standard_scanner
from leo.storage import ScannerAnalysisStore, ScannerIqStore, live_scanner_analysis_source
from leo.storage.errors import BundleNotFoundError


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan_ids", nargs="+")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--output-root",
        type=Path,
        help="separate bulk root for validation; defaults to --bulk-root",
    )
    parser.add_argument("--analysis-id", default=STANDARD_SCANNER_ANALYSIS_ID)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    iq_store = ScannerIqStore(arguments.bulk_root)
    analysis_store = ScannerAnalysisStore(arguments.output_root or arguments.bulk_root)
    results = []
    for scan_id in arguments.scan_ids:
        bundle = iq_store.inspect(scan_id)
        try:
            existing = analysis_store.inspect(scan_id, arguments.analysis_id)
        except BundleNotFoundError:
            existing = None
        if existing is not None:
            if (
                existing.metrics.input_uri != bundle.uri
                or existing.metrics.input_manifest_sha256 != bundle.manifest_sha256
            ):
                raise ValueError("existing scanner analysis has different input evidence")
            item = {
                "scan_id": scan_id,
                "analysis_id": arguments.analysis_id,
                "state": "reused",
                "uri": existing.uri,
                "manifest_sha256": existing.manifest_sha256,
            }
            results.append(item)
            print(json.dumps(item, sort_keys=True), flush=True)
            continue

        total_started = time.perf_counter()
        source_started = time.perf_counter()
        source = live_scanner_analysis_source(
            iq_store,
            bundle,
            capture_elapsed_ms=_capture_elapsed_ms(bundle.manifest.frames),
        )
        source_elapsed_s = time.perf_counter() - source_started
        analysis_started = time.perf_counter()
        result = analyze_standard_scanner(source)
        analysis_elapsed_s = time.perf_counter() - analysis_started
        render_started = time.perf_counter()
        waterfall_png = render_scanner_waterfall_png(result.metrics)
        glrt64_png = render_scanner_glrt64_response_png(
            result.metrics,
            result.pilot_doppler,
        )
        pilot_png = render_scanner_pilot_doppler_png(
            result.metrics,
            result.pilot_doppler,
        )
        pilot_carrier_tracking_png = render_scanner_pilot_carrier_tracking_png(
            result.metrics,
            result.pilot_doppler,
        )
        pilot_segment_rates_png = render_scanner_pilot_segment_rates_png(
            result.metrics,
            result.pilot_doppler,
        )
        render_elapsed_s = time.perf_counter() - render_started
        publish_started = time.perf_counter()
        published = analysis_store.publish(
            arguments.analysis_id,
            result.report,
            result.metrics,
            waterfall_png=waterfall_png,
            glrt64_png=glrt64_png,
            pilot_doppler=result.pilot_doppler,
            pilot_doppler_png=pilot_png,
            pilot_carrier_tracking_png=pilot_carrier_tracking_png,
            pilot_segment_rates_png=pilot_segment_rates_png,
        )
        publish_elapsed_s = time.perf_counter() - publish_started
        item = {
            "scan_id": scan_id,
            "analysis_id": arguments.analysis_id,
            "state": "published",
            "uri": published.uri,
            "manifest_sha256": published.manifest_sha256,
            "source_elapsed_s": source_elapsed_s,
            "analysis_elapsed_s": analysis_elapsed_s,
            "render_elapsed_s": render_elapsed_s,
            "publish_elapsed_s": publish_elapsed_s,
            "total_elapsed_s": time.perf_counter() - total_started,
            "active_edges": len(result.report.active_edges),
            "confirmed_receiver_tracks": (result.pilot_doppler.confirmed_receiver_track_count),
            "pilot_segments": result.pilot_doppler.analyzed_segment_count,
            "qualified_pilot_segments": result.pilot_doppler.qualified_segment_count,
        }
        results.append(item)
        print(json.dumps(item, sort_keys=True), flush=True)
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


def _capture_elapsed_ms(frames) -> float:
    lower = min(frame.host_request_monotonic_ns_lower for frame in frames)
    upper = max(frame.host_request_monotonic_ns_upper for frame in frames)
    return max(0.0, (upper - lower) / 1_000_000)


if __name__ == "__main__":
    raise SystemExit(main())
