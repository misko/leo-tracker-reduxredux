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
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def geometry(catalogue, indices, origin, times, receiver, up):
    position, velocity, valid = propagate_candidate_states(
        catalogue, indices, origin, times, np.array([0.0])
    )
    delta = position[:, 0] - receiver
    direction = delta / np.linalg.norm(delta, axis=-1)[..., None]
    fraction = -np.sum(direction * velocity[:, 0], axis=-1) / 299792.458
    elevation = np.rad2deg(np.arcsin(np.clip(np.sum(direction * up, axis=-1), -1, 1)))
    return fraction, elevation, valid


def main():
    previous = ROOT.parent / "2026_10_02_shared_rx_position"
    receipt = json.loads((previous / "inputs.json").read_text())
    solution = json.loads((previous / "results.json").read_text())["models"]["linear"]
    reader = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = reader.load(receipt["session_id"])
    finally:
        reader.close()
    assert source.input_manifest_sha256 == receipt["input_manifest"]
    assert source.analysis_manifest_sha256 == receipt["analysis_manifest"]
    candidates = project_scanner_candidates(source)
    origin = source.timing.first_sample_estimate_utc_ns
    assert origin == receipt["start_utc_ns"]
    trajectory = reconstruct_persistent_hop_trajectories(
        candidates, config=PersistentHopTrajectoryConfig()
    )
    previous_ids = {track["track_id"] for track in solution["tracks"]}
    accepted_ids = {track["track_id"] for track in solution["tracks"] if track["accepted"]}
    old_points = {
        point.candidate_id
        for track in trajectory.tracklets
        if track.tracklet_id in previous_ids
        for point in track.points
    }
    accepted_points = {
        point.candidate_id
        for track in trajectory.tracklets
        if track.tracklet_id in accepted_ids
        for point in track.points
    }
    old_groups = {row.source_group_id for row in candidates if row.candidate_id in old_points}
    accepted_groups = {
        row.source_group_id for row in candidates if row.candidate_id in accepted_points
    }
    groups = sorted({row.source_group_id for row in candidates})
    group_indices = {value: index for index, value in enumerate(groups)}
    times = np.array([(row.support_center_utc_ns - origin) / 1e9 for row in candidates])
    arrays = {
        "times": times,
        "measured": np.array([row.measured_cfo_hz for row in candidates]),
        "rf": np.array([row.actual_rf_hz for row in candidates]),
        "channel": np.array([row.channel for row in candidates]),
        "receiver": np.array([row.receiver_id for row in candidates]),
        "group": np.array([group_indices[row.source_group_id] for row in candidates]),
        "margin": np.array([row.margin for row in candidates]),
        "old_group": np.array([row.source_group_id in old_groups for row in candidates]),
        "accepted_old_group": np.array(
            [row.source_group_id in accepted_groups for row in candidates]
        ),
    }
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == receipt["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = [
        index for index, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")
    ]
    receiver = geodetic_to_ecef_km(solution["latitude"], solution["longitude"], 0)
    latitude, longitude = np.deg2rad([solution["latitude"], solution["longitude"]])
    up = np.array(
        [
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        ]
    )
    nodes = np.arange(0, 300.0001, 0.5)
    fractions, elevations, retained = [], [], []
    for start in range(0, len(indices), 128):
        fraction, elevation, valid = geometry(
            catalogue, indices[start : start + 128], origin, nodes, receiver, up
        )
        keep = np.any(elevation >= 0, axis=1)
        fractions.extend(fraction[keep])
        elevations.extend(elevation[keep])
        retained.extend(valid[keep])
    numbers = np.array(catalogue.satellite_numbers)[retained]
    arrays.update(
        nodes=nodes, fractions=np.array(fractions), elevations=np.array(elevations), numbers=numbers
    )
    selected = sorted(
        {track["catalog_number"] for track in solution["tracks"] if track["accepted"]}
    )
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    exact_fraction, exact_elevation, valid = geometry(
        catalogue, [lookup[number] for number in selected], origin, times, receiver, up
    )
    assert list(valid) == [lookup[number] for number in selected]
    assert set(selected).issubset(set(numbers))
    arrays.update(
        selected_numbers=np.array(selected),
        exact_fraction=exact_fraction,
        exact_elevation=exact_elevation,
    )
    interpolation_errors = []
    for index, number in enumerate(selected):
        grid_index = int(np.flatnonzero(numbers == number)[0])
        interpolated = np.interp(times, nodes, arrays["fractions"][grid_index])
        interpolation_errors.extend(np.abs(interpolated - exact_fraction[index]) * arrays["rf"])
    np.savez_compressed(ROOT / "inputs.npz", **arrays)
    output = {
        "session_id": receipt["session_id"],
        "source": receipt,
        "solution": solution,
        "selected_satellites": selected,
        "catalogue_eligible_count": len(indices),
        "visible_satellites": len(numbers),
        "projected_candidate_count": len(candidates),
        "source_group_count": len(groups),
        "scope": (
            "all stored gate-passing nonoverlapping GLRT projections; not subthreshold bins or IQ"
        ),
        "candidate_ids": [row.candidate_id for row in candidates],
        "source_group_ids": groups,
        "curve_interpolation_max_error_hz_selected": float(max(interpolation_errors)),
    }
    (ROOT / "inputs.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    "visible_satellites",
                    "projected_candidate_count",
                    "source_group_count",
                    "curve_interpolation_max_error_hz_selected",
                )
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
