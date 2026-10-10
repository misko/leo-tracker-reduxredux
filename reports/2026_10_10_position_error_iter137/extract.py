"""Metadata-only selected-state projection of the full frozen cohort."""

import json
from pathlib import Path

from project import read_selected

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parent / "2026_10_09_position_error_iter107"


def main():
    authority = json.loads((HERE / "source-feasibility.json").read_text())
    output = HERE / "selected"
    output.mkdir(exist_ok=True)
    counts = {}
    for member in authority["members"]:
        label = member["label"]
        destination = output / (label + ".json")
        if destination.exists():
            raise ValueError("Projection already exists; no silent overwrite")
        projection = read_selected(UPSTREAM / "results" / label / "candidate.json")
        if projection["label"] != label or projection["phase"] != "candidate":
            raise ValueError("Candidate identity mismatch")
        projection["session_id"] = member["session_id"]
        with destination.open("x") as stream:
            json.dump(projection, stream, indent=2, allow_nan=False)
            stream.write("\n")
        stage = projection["operational"]["fitted-c"]["selection"]["accepted_stage"]
        counts[stage] = counts.get(stage, 0) + 1
    print(json.dumps({"members": len(authority["members"]), "fitted_selected_stages": counts}))


if __name__ == "__main__":
    main()
