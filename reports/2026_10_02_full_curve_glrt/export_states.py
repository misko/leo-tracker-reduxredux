import json
from pathlib import Path

import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def main():
    data = np.load(ROOT / "inputs.npz")
    metadata = json.loads((ROOT / "inputs.json").read_text())
    origin = metadata["source"]["start_utc_ns"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == metadata["source"]["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    indices = [lookup[int(number)] for number in data["selected_numbers"]]
    position, velocity, valid = propagate_candidate_states(
        catalogue, indices, origin, data["times"], np.array([0.0])
    )
    assert list(valid) == indices
    np.savez_compressed(
        ROOT / "position-states.npz",
        position=position[:, 0].transpose(1, 0, 2),
        velocity=velocity[:, 0].transpose(1, 0, 2),
        numbers=data["selected_numbers"],
    )
    print(json.dumps({"satellites": len(indices), "observation_candidates": len(data["times"])}))


if __name__ == "__main__":
    main()
