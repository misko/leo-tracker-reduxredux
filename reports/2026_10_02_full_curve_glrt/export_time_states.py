import argparse
import json
from pathlib import Path

import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bound-seconds", type=float, default=3)
    parser.add_argument("--output", default="satellite-time-states.npz")
    args = parser.parse_args()
    if args.bound_seconds <= 0:
        parser.error("bound must be positive")
    metadata = json.loads((ROOT / "inputs.json").read_text())
    selection = json.loads((ROOT / "satellite-sweep-selection.json").read_text())
    numbers = selection["subsets"]["64"]
    origin = metadata["source"]["start_utc_ns"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == metadata["source"]["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    indices = [lookup[number] for number in numbers]
    times = np.arange(-args.bound_seconds - 1, 301.001 + args.bound_seconds, 0.25)
    position, velocity, valid = propagate_candidate_states(
        catalogue, indices, origin, times, np.array([0.0])
    )
    assert list(valid) == indices
    np.savez_compressed(
        ROOT / args.output,
        nodes=times,
        position=position[:, 0],
        velocity=velocity[:, 0],
        numbers=numbers,
    )
    print(json.dumps({"satellites": len(numbers), "nodes": len(times)}))


if __name__ == "__main__":
    main()
