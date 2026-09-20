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


def recorded_clock_bounds(data, assignments, timing_rows, evidence):
    """Bind each numerical session group to its actual observation reference UTC."""
    timings = {r["session_id"]: r["timing"] for r in timing_rows}
    if len(timings) != len(timing_rows):
        raise ValueError("duplicate timing session")
    bounds = {}
    for group in np.unique(data["session"]):
        episodes = np.unique(data["episode"][data["session"] == group])
        sessions = {assignments[int(i)]["session_id"] for i in episodes}
        if len(sessions) != 1:
            raise ValueError("clock group spans multiple recording identities")
        sid = sessions.pop()
        timing = timings[sid]
        doc = json.loads((evidence / "evidence" / (sid + ".json")).read_text())
        reference = doc["inventory"]["reference_utc_ns"]
        if reference != timing["first_sample_estimate_utc_ns"]:
            raise ValueError("recording timing reference differs from evidence UTC")
        bounds[int(group)] = tuple(
            (timing[key] - reference) / 1e9
            for key in ["first_sample_earliest_utc_ns", "first_sample_latest_utc_ns"]
        )
    return bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--stability", action="store_true")
    parser.add_argument("--timing-audit", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent = json.loads((args.run / "inference.json").read_text())
    data = dict(np.load(args.run / "states.npz"))
    bounds = None
    if args.timing_audit:
        if args.evidence is None:
            raise ValueError("timing audit requires evidence UTC references")
        bounds = recorded_clock_bounds(
            data, parent["assignments"], json.loads(args.timing_audit.read_text()), args.evidence
        )
    ids = [
        i for i, row in enumerate(parent["assignments"]) if row in parent["selected_assignments"]
    ]
    output = dict(
        evaluation_location_used=False,
        parent_digest=digest(args.run / "inference.json"),
        states_digest=digest(args.run / "states.npz"),
        clock_bounds_s=bounds if bounds is not None else [-0.5, 0.5],
        timing_audit_digest=digest(args.timing_audit) if args.timing_audit else None,
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
            clock_bounds=bounds,
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
    if args.stability:
        output["stability"] = []
        base = np.isin(data["episode"], ids)
        for grouping in ["norad", "session"]:
            for fold in range(8):
                mask = base & (data[grouping] % 8 != fold)
                result = fit(
                    data,
                    Region(**parent["region"]),
                    parent["initial"],
                    "observation",
                    True,
                    subset=mask,
                    fit_clock=True,
                    clock_groups=data["session"],
                    clock_bounds=bounds,
                )
                output["stability"].append(dict(grouping=grouping, fold=fold, **result))
                print(grouping, fold, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(args.output, output)


if __name__ == "__main__":
    main()
