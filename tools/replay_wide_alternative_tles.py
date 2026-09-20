"""Offline orbit sensitivity with frozen independent-wide IDs and RF evidence."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def validate_assignment_order(assignments, rows):
    def keys(r):
        return r["session_id"], r["episode_id"], r["norad"]
    if [keys(a) for a in assignments] != [keys(r) for r in rows]:
        raise ValueError("audit assignment order or identity differs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["run", "audit", "evidence", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("fresh output required")
    parent_path = args.run / "inference.json"
    parent = json.loads(parent_path.read_text())
    audit = json.loads(args.audit.read_text())
    if audit["assignments_digest"] != digest(parent_path):
        raise ValueError("audit parent digest differs")
    if (
        not parent["complete"]
        or parent["position_truth_used"]
        or parent["prior_matched_norads_used"]
    ):
        raise ValueError("completed independent parent required")
    validate_assignment_order(parent["assignments"], audit["rows"])
    data = dict(np.load(args.run / "states.npz"))
    out = dict(
        evaluation_location_used=False,
        offline_noncausal=audit["offline_noncausal"],
        parent_digest=digest(parent_path),
        audit_digest=digest(args.audit),
        states_digest=digest(args.run / "states.npz"),
        invalid_replacements=[],
        models=[],
    )
    differences = []
    for i, row in enumerate(audit["rows"]):
        mask = data["episode"] == i
        doc = json.loads((args.evidence / "evidence" / (row["session_id"] + ".json")).read_text())
        arc = dict(load_observations(doc, 0))[row["episode_id"]]
        if not np.array_equal(arc.frequency_hz, data["y"][mask]) or not np.array_equal(
            arc.training, data["training"][mask]
        ):
            raise ValueError("RF evidence/partition mismatch")
        if row["measurement_utc_ns"] != doc["inventory"]["reference_utc_ns"]:
            raise ValueError("measurement UTC mismatch")
        cat = parse_element_sets(row["selected"]["text"])
        if cat.satellite_numbers != (row["norad"],):
            raise ValueError("replacement NORAD differs")
        replacements = {}
        for shift in [0.0, -0.5, 0.5]:
            p, v, valid = state_arrays(
                cat, [0], row["measurement_utc_ns"], arc.time_s, clock_s=shift
            )
            if len(valid) != 1:
                break
            suffix = "" if shift == 0 else str(shift)
            replacements["p" + suffix], replacements["v" + suffix] = p[0], v[0]
        if len(replacements) != 6:
            out["invalid_replacements"].append(i)
            continue
        differences.extend(np.linalg.norm(replacements["p"] - data["p"][mask], axis=1) * 1000)
        for key, value in replacements.items():
            data[key][mask] = value
    out["state_displacement_m"] = dict(
        median=float(np.median(differences)), maximum=float(np.max(differences))
    )
    ids = [i for i, a in enumerate(parent["assignments"]) if a in parent["selected_assignments"]]
    for selection, mask in [("all", None), ("selected", np.isin(data["episode"], ids))]:
        for clock in [False, True]:
            result = fit(
                data,
                Region(**parent["region"]),
                parent["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=clock,
            )
            out["models"].append(dict(selection=selection, **result))
            print(selection, clock, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(args.output, out)


if __name__ == "__main__":
    main()
