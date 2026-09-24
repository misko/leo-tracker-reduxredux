#!/usr/bin/env python3
"""Export compact, causal fixed-identity DS2 geometry inputs as JSON.

This program is intentionally run as the read-only ``leo`` service account.
It does not write under the bulk root.  Its JSON stdout is redirected by the
caller into this report directory, which keeps the copied numerical evidence
small, immutable, and auditable.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.operations.scan_position_inputs import prepare_scan_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

SESSIONS = (
    "scan-fw-f3ce5fe73aa40506",
    "scan-fw-9f3d5067d149118e",
    "scan-fw-cfcf667726e80735",
)


def values(value):
    return np.asarray(value).tolist()


def receiver_ids(product) -> dict[str, int]:
    return {item.tracklet_id: item.receiver_id for item in product.tracklets}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    inputs = ScannerTrackingInputStore(args.bulk_root)
    products = ScannerTrackingStore(args.bulk_root)
    archive = TleArchiveReader(args.tle_root)
    try:
        scans = []
        for session_id in SESSIONS:
            status = products.status(session_id)
            if status.state != "complete" or status.product is None:
                raise ValueError(f"tracking product unavailable: {session_id}")
            prepared = prepare_scan_position_inputs(
                session_id,
                inputs=inputs,
                products=products,
                archive=archive,
                maximum_target_tracks=64,
                history_hours=1.0,
                maximum_history_sessions=0,
                maximum_total_tracks=64,
                maximum_observations_per_track=512,
            )
            labels = receiver_ids(status.product)
            episodes = []
            for item in prepared.target_episodes:
                receiver_id = labels.get(item.track_id.removeprefix(f"{session_id}:"))
                if receiver_id not in (0, 1):
                    raise ValueError(f"receiver label absent for {session_id}/{item.track_id}")
                episodes.append(
                    {
                        "track_id": item.track_id,
                        "pass_id": item.pass_id,
                        "receiver_id": receiver_id,
                        "observation_id": values(item.observation_id),
                        "observed_hz": values(item.observed_hz),
                        "training": values(item.training),
                        "time_s": values(item.time_s),
                        "candidate_id": values(item.candidate_id),
                        "position_ecef_km": values(item.position_ecef_km),
                        "velocity_ecef_km_s": values(item.velocity_ecef_km_s),
                        "catalogue_size": item.catalogue_size,
                    }
                )
            scans.append(
                {
                    "session_id": session_id,
                    "input_manifest_sha256": status.product.input_manifest_sha256,
                    "analysis_manifest_sha256": status.product.analysis_manifest_sha256,
                    "tracking_product_sha256": status.product.analysis_manifest_sha256,
                    "tracking_configuration_digest": status.product.configuration_digest,
                    "tle_snapshot": status.product.original_tle_snapshot.model_dump(mode="json"),
                    "episode_count": len(episodes),
                    "episodes": episodes,
                    "exclusions": [asdict(item) for item in prepared.exclusions],
                }
            )
        print(
            json.dumps(
                {
                    "schema": "ds2-geometry-cone-causal-inputs/v1",
                    "identity_policy": "saved-site-assisted-leading-candidate; conditional-only",
                    "history_policy": "target-session-only",
                    "sessions": scans,
                },
                sort_keys=True,
            )
        )
    finally:
        inputs.close()


if __name__ == "__main__":
    main()
