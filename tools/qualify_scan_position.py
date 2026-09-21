"""Replay bounded position diagnostics from published tracking; no RF acquisition."""

import argparse
import json
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.operations.scanner_position import build_scan_position_diagnostic
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--session-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= len(args.session_id) <= 4:
        parser.error("qualify one to four retained scans")
    args.output.mkdir(parents=True, exist_ok=True)
    inputs = ScannerTrackingInputStore(args.bulk_root)
    products = ScannerTrackingStore(args.bulk_root)
    archive = TleArchiveReader(args.tle_root)
    snapshots = {s.digest: s for s in archive.list_snapshots()}
    summaries = []
    try:
        for session_id in args.session_id:
            source = inputs.load(session_id)
            product = products.status(session_id).product
            if product is None or product.input_manifest_sha256 != source.input_manifest_sha256:
                raise ValueError("tracking is missing or capture authority differs")
            if product.analysis_manifest_sha256 != source.analysis_manifest_sha256:
                raise ValueError("tracking analysis authority differs")
            trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
            snapshot = product.original_tle_snapshot
            payload = archive.read(snapshots[snapshot.digest]) if snapshot is not None else None
            diagnostic, png = build_scan_position_diagnostic(
                source=source,
                trajectory=trajectory,
                product=product,
                catalogue_payload=payload,
            )
            row = {
                "session_id": session_id,
                "position_diagnostic": diagnostic.model_dump(mode="json"),
            }
            (args.output / f"{session_id}.json").write_text(json.dumps(row, indent=2) + "\n")
            (args.output / f"{session_id}.png").write_bytes(png)
            summaries.append(row)
            print(json.dumps(row), flush=True)
    finally:
        inputs.close()
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
