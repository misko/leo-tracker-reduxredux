#!/usr/bin/env python3
"""Run replay sweeps through the segmented Standard scanner analysis pipeline."""

from __future__ import annotations

import argparse
import json
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
from leo.storage import (
    ScannerAnalysisStore,
    ScannerReplayStore,
    replay_scanner_analysis_source,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_ids", nargs="+")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--analysis-id", default=STANDARD_SCANNER_ANALYSIS_ID)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    replay_store = ScannerReplayStore(arguments.bulk_root)
    analysis_store = ScannerAnalysisStore(arguments.bulk_root)
    published = []
    for dataset_id in arguments.dataset_ids:
        dataset = replay_store.inspect(dataset_id)
        for entry in dataset.manifest.entries:
            sweep = replay_store.inspect_sweep(dataset_id, entry.sweep_id)
            source = replay_scanner_analysis_source(replay_store, sweep)
            result = analyze_standard_scanner(source)
            bundle = analysis_store.publish(
                arguments.analysis_id,
                result.report,
                result.metrics,
                waterfall_png=render_scanner_waterfall_png(result.metrics),
                glrt64_png=render_scanner_glrt64_response_png(
                    result.metrics,
                    result.pilot_doppler,
                ),
                pilot_doppler=result.pilot_doppler,
                pilot_doppler_png=render_scanner_pilot_doppler_png(
                    result.metrics,
                    result.pilot_doppler,
                ),
                pilot_carrier_tracking_png=render_scanner_pilot_carrier_tracking_png(
                    result.metrics,
                    result.pilot_doppler,
                ),
                pilot_segment_rates_png=render_scanner_pilot_segment_rates_png(
                    result.metrics,
                    result.pilot_doppler,
                ),
            )
            published.append(
                {
                    "dataset_id": dataset_id,
                    "sweep_id": entry.sweep_id,
                    "split": entry.split.value,
                    "scan_id": bundle.scan_id,
                    "uri": bundle.uri,
                    "manifest_sha256": bundle.manifest_sha256,
                    "active_edges": len(result.report.active_edges),
                }
            )
            print(json.dumps(published[-1], sort_keys=True), flush=True)
    print(json.dumps({"published": len(published), "analyses": published}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
