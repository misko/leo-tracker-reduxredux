"""Fit independent recording UTC corrections after a completed wide search.

Identities and quality selection remain frozen from the parent inference.
No evaluation coordinate is accepted or read.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import extract, fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent = json.loads((args.run / "inference.json").read_text())
    data = dict(np.load(args.run / "states.npz"))
    ids = [
        i for i, row in enumerate(parent["assignments"]) if row in parent["selected_assignments"]
    ]
    output = dict(
        evaluation_location_used=False,
        parent_digest=digest(args.run / "inference.json"),
        states_digest=digest(args.run / "states.npz"),
        clock_bounds_s=[-0.5, 0.5],
        models=[],
    )
    for selection, mask in [("all", None), ("selected", np.isin(data["episode"], ids))]:
        result = fit(
            data,
            Region(**parent["region"]),
            parent["initial"],
            "observation",
            True,
            subset=mask,
            fit_clock=True,
            clock_groups=data["session"],
        )
        if args.evidence is not None:
            exact_data = {key: value.copy() for key, value in data.items()}
            selected = np.ones(len(data["y"]), bool) if mask is None else mask
            for session, tau in zip(
                result["clock_group_values"], result["clock_offsets_s"], strict=True
            ):
                chosen = selected & (data["session"] == session)
                episodes = np.unique(data["episode"][chosen])
                assignments = [parent["assignments"][int(i)] for i in episodes]
                exact, _ = extract(args.evidence, assignments, clock_s=tau)
                if not np.array_equal(exact["y"], data["y"][chosen]):
                    raise ValueError("exact propagation observation order differs")
                for key in ["p", "v"]:
                    exact_data[key][chosen] = exact[key]
            result["exact_clock_refit"] = fit(
                exact_data,
                Region(**parent["region"]),
                result["x_km"][:2],
                "observation",
                True,
                subset=mask,
            )
        output["models"].append(dict(selection=selection, **result))
        print(selection, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(args.output, output)


if __name__ == "__main__":
    main()
