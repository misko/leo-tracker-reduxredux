import json
from pathlib import Path

import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.operations.adaptive_tle_position_inputs import _graphs
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def main():
    saved = json.loads(
        (ROOT.parent / "2026_10_01_channel1_rx0_track_audit/offset-source.json").read_text()
    )
    product = saved["product"]
    reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = reader.load(saved["session_id"])
    finally:
        reader.close()
    assert source.input_manifest_sha256 == product["input_manifest_sha256"]
    assert source.analysis_manifest_sha256 == product["analysis_manifest_sha256"]
    origin = source.timing.first_sample_estimate_utc_ns
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(source), config=PersistentHopTrajectoryConfig()
    )
    graphs = dict(_graphs(trajectory))
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == product["original_tle_snapshot"]["digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    tracklets = {track["tracklet_id"]: track for track in product["tracklets"]}
    arrays = {
        key: [] for key in ("times", "measured", "receiver", "track", "rf", "position", "velocity")
    }
    metadata, observed = [], set()
    for track_index, review in enumerate(product["track_reviews"]):
        track_id = review["tracklet_id"]
        track = tracklets[track_id]
        rows = sorted(graphs[track_id].observations, key=lambda row: row.support_center_utc_ns)
        observation_ids = [row.observation_id for row in rows]
        assert len(rows) == review["observation_count"]
        assert not observed.intersection(observation_ids)
        observed.update(observation_ids)
        times = np.array([(row.support_center_utc_ns - origin) / 1e9 for row in rows])
        numbers = [candidate["catalog_number"] for candidate in review["candidates"]]
        selected = [indices[number] for number in numbers]
        position, velocity, valid = propagate_candidate_states(
            catalogue, selected, origin, times, np.array([0.0])
        )
        assert list(valid) == selected
        arrays["times"].append(times)
        arrays["measured"].append(
            np.array([row.measured_cfo_hz for row in rows]) * track["actual_rf_hz"] / 11.2e9
        )
        arrays["receiver"].append(np.full(len(rows), track["receiver_id"]))
        arrays["track"].append(np.full(len(rows), track_index))
        arrays["rf"].append(np.full(len(rows), track["actual_rf_hz"]))
        arrays["position"].append(position[:, 0].transpose(1, 0, 2))
        arrays["velocity"].append(velocity[:, 0].transpose(1, 0, 2))
        metadata.append(
            {
                "track_id": track_id,
                "catalog_numbers": numbers,
                "channel": track["channel"],
                "receiver": track["receiver_id"],
                "observation_ids": observation_ids,
            }
        )
    np.savez_compressed(
        ROOT / "inputs.npz", **{key: np.concatenate(value) for key, value in arrays.items()}
    )
    receipt = {
        "session_id": saved["session_id"],
        "input_manifest": source.input_manifest_sha256,
        "analysis_manifest": source.analysis_manifest_sha256,
        "snapshot_digest": snapshot.digest,
        "start_utc_ns": origin,
        "tracks": metadata,
        "timing": "zero shift for all candidates",
        "selection": (
            "persisted fixed-site top-five review shortlist; conditional, not blind localization"
        ),
        "reference_site": product["observer_site"],
    }
    (ROOT / "inputs.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"tracks": len(metadata), "observations": len(observed)}), flush=True)


if __name__ == "__main__":
    main()
