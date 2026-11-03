import hashlib
import json
from pathlib import Path

import numpy as np
from common import ROOT, SOURCE, Data, coordinates, ecef
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def main():
    result = json.loads((ROOT / "results.json").read_text())
    metadata = json.loads((SOURCE / "inputs.json").read_text())
    origin = metadata["source"]["start_utc_ns"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == metadata["source"]["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    data = Data()
    audit = {
        "stages": {},
        "code_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(ROOT.glob("*.py"))
        },
    }
    for name, stage in result["stages"].items():
        path = ROOT / ("anchors.json" if name == "anchors" else "extensions.json")
        assignment = json.loads(path.read_text())
        rows = np.asarray(assignment["rows"], dtype=int)
        satellites = np.asarray(assignment["satellites"], dtype=int)
        assert len(np.unique(data.group[rows])) == len(rows)
        parameters = np.asarray(stage["fit"]["parameters"])
        prediction, visible = data.predict(parameters, rows, satellites)
        latitude, longitude = coordinates(parameters[:2])
        receiver = ecef(latitude, longitude)
        latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
        up = np.array(
            [
                np.cos(latitude_rad) * np.cos(longitude_rad),
                np.cos(latitude_rad) * np.sin(longitude_rad),
                np.sin(latitude_rad),
            ]
        )
        maximum_error = 0.0
        visibility_disagreements = 0
        for satellite in np.unique(satellites):
            mask = satellites == satellite
            chosen = rows[mask]
            index = lookup[int(data.numbers[satellite])]
            position, velocity, valid = propagate_candidate_states(
                catalogue,
                [index],
                origin,
                data.times[chosen],
                np.array([parameters[6 + satellite]]),
            )
            assert list(valid) == [index]
            delta = position[0, 0] - receiver
            direction = delta / np.linalg.norm(delta, axis=1)[:, None]
            correction = parameters[2 + 2 * data.receiver[chosen]] + parameters[
                3 + 2 * data.receiver[chosen]
            ] * (data.times[chosen] - 150)
            exact = (
                -data.rf[chosen] * np.sum(direction * velocity[0, 0], axis=1) / 299792.458
                + correction
            )
            maximum_error = max(maximum_error, float(np.max(np.abs(prediction[mask] - exact))))
            visibility_disagreements += int(np.sum(visible[mask] != (direction @ up >= 0)))
        assert maximum_error < 1.0
        assert visibility_disagreements == 0
        audit["stages"][name] = {
            "unique_assigned_groups": len(rows),
            "maximum_interpolation_error_hz": maximum_error,
            "visibility_disagreements": visibility_disagreements,
        }
    (ROOT / "exact-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit["stages"]))


if __name__ == "__main__":
    main()
