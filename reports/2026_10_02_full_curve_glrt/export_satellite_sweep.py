import json
from pathlib import Path

import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from matching import assign_groups, circular_residual, connected_support

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def main():
    data = np.load(ROOT / "inputs.npz")
    metadata = json.loads((ROOT / "inputs.json").read_text())
    offsets = np.zeros(len(data["times"]))
    for receiver in (0, 1):
        mask = data["receiver"] == receiver
        parameters = metadata["solution"]["parameters"][str(receiver)]
        offsets[mask] = parameters["intercept_hz_at_150s"] + parameters["slope_hz_s"] * (
            data["times"][mask] - 150
        )
    ranking = []
    for index, number in enumerate(data["numbers"]):
        prediction = (
            np.interp(data["times"], data["nodes"], data["fractions"][index]) * data["rf"] + offsets
        )
        elevation = np.interp(data["times"], data["nodes"], data["elevations"][index])
        residual = circular_residual(data["measured"], prediction)
        residual[elevation < 0] = np.inf
        assignment = assign_groups(residual[None, :], data["group"])
        coherent, segments = connected_support(
            assignment, data["times"], data["channel"], data["receiver"]
        )
        ranking.append(
            {
                "catalog_number": int(number),
                "coherent_groups": int(coherent.sum()),
                "gate_groups": int(assignment["accepted"].sum()),
                "segments": len(segments),
            }
        )
    ranking.sort(
        key=lambda row: (-row["coherent_groups"], -row["gate_groups"], row["catalog_number"])
    )
    original = set(map(int, data["selected_numbers"]))
    nested = [row for row in ranking if row["catalog_number"] in original] + [
        row for row in ranking if row["catalog_number"] not in original
    ]
    chosen = [row["catalog_number"] for row in nested[:64]]
    assert set(chosen[:16]) == original
    selection = {
        "policy": (
            "nested prefixes: original 16 first, ranked by individual continuous GLRT support "
            "at frozen starting solution; remaining visible satellites ranked identically; "
            "ties use gate count then catalogue ID"
        ),
        "coherence": (
            "1000Hz gate, >=8 groups over >=10s, gaps <=4s, separately per CH/RX; "
            "no exclusivity between satellites during ranking"
        ),
        "scope": (
            "data-dependent conditional shortlist, fixed before position search; "
            "original 16-set preserved"
        ),
        "ranking": nested,
        "subsets": {str(count): chosen[:count] for count in (8, 16, 32, 64)},
    }
    (ROOT / "satellite-sweep-selection.json").write_text(json.dumps(selection, indent=2) + "\n")
    origin = metadata["source"]["start_utc_ns"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == metadata["source"]["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    indices = [lookup[number] for number in chosen]
    position, velocity, valid = propagate_candidate_states(
        catalogue, indices, origin, data["times"], np.array([0.0])
    )
    assert list(valid) == indices
    np.savez_compressed(
        ROOT / "satellite-sweep-states.npz",
        position=position[:, 0].transpose(1, 0, 2),
        velocity=velocity[:, 0].transpose(1, 0, 2),
        numbers=np.array(chosen),
    )
    print(json.dumps(selection["subsets"]), flush=True)


if __name__ == "__main__":
    main()
