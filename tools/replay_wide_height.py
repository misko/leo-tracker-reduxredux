"""Evaluate free receiver height using frozen identities from a wide search."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import extract, fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "evidence", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    parent = json.loads((a.run / "inference.json").read_text())
    data = dict(np.load(a.run / "states.npz"))
    selected = parent["selected_assignments"]
    indices = [i for i, row in enumerate(parent["assignments"]) if row in selected]
    mask = np.isin(data["episode"], indices)
    region = Region(**parent["region"])
    result = dict(
        parent_digest=digest(a.run / "inference.json"),
        states_digest=digest(a.run / "states.npz"),
        evaluation_location_used=False,
        altitude_bounds_m=[-500, 5000],
        models=[],
    )
    for selection, subset in [("all", None), ("selected", mask)]:
        for clock in [False, True]:
            row = fit(
                data,
                region,
                parent["initial"],
                "observation",
                True,
                subset=subset,
                fit_clock=clock,
                fit_height=True,
            )
            if selection == "selected" and clock:
                exact, _ = extract(a.evidence, selected, clock_s=row["clock_s"])
                row["exact_clock_refit"] = fit(
                    exact, region, row["x_km"][:2], "observation", True, fit_height=True
                )
            result["models"].append(dict(selection=selection, **row))
            print(
                selection,
                clock,
                row["latitude_deg"],
                row["longitude_deg"],
                row["altitude_m"],
                row["clock_s"],
                flush=True,
            )
    write_json(a.output, result)


if __name__ == "__main__":
    main()
