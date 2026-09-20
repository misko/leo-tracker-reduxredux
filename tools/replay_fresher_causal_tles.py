"""Controlled replay replacing only strictly newer, already available TLE epochs."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, state_arrays, write_json

from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["audit", "states", "evidence", "parent", "information", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    audit = json.loads(a.audit.read_text())
    d = dict(np.load(a.states))
    output = dict(
        input_digests={str(p): digest(p) for p in [a.audit, a.states, a.parent, a.information]},
        identity_provenance="fixed known-site FoV-assisted IDs; conditional orbit-quality test",
        evaluation_location_used=False,
        replaced=[],
        rejected_updates=[],
        models=[],
    )
    if len(audit["rows"]) != len(np.unique(d["segment"])):
        raise ValueError("assignment count mismatch")
    for i, row in enumerate(audit["rows"]):
        mask = d["segment"] == i
        if not np.all(d["norad"][mask] == row["norad"]):
            raise ValueError("assignment identity mismatch")
        if not row["strictly_newer_epoch"]:
            continue
        selected = row["selected"]
        if not (
            row["nominal_epoch_utc_ns"] < selected["epoch_utc_ns"] < row["measurement_utc_ns"]
            and selected["collected_utc_ns"] < row["measurement_utc_ns"]
        ):
            raise ValueError("non-causal or non-newer update")
        path = a.evidence / "evidence" / (row["session_id"] + ".json")
        doc = json.loads(path.read_text())
        arc = dict(load_observations(doc, 0))[row["episode_id"]]
        if not (
            np.array_equal(arc.frequency_hz, d["y"][mask])
            and np.array_equal(arc.training, d["training"][mask])
        ):
            raise ValueError("RF order/partition mismatch")
        cat = parse_element_sets(selected["text"])
        if list(cat.satellite_numbers) != [row["norad"]]:
            raise ValueError("replacement element identity mismatch")
        updates = {}
        for clock in [-0.5, 0.0, 0.5]:
            p, v, valid = state_arrays(
                cat, [0], row["measurement_utc_ns"], arc.time_s, clock_s=clock
            )
            if len(valid) != 1:
                break
            updates["p" + str(clock)] = p[0]
            updates["v" + str(clock)] = v[0]
        if len(updates) != 6:
            output["rejected_updates"].append(dict(segment=i, reason="invalid propagated update"))
            continue
        for key, value in updates.items():
            d[key][mask] = value
        output["replaced"].append(i)
    d["p"], d["v"], d["episode"] = d["p0.0"], d["v0.0"], d["segment"]
    parent = json.loads(a.parent.read_text())["cohorts"]["current_fov_selected"]
    rows = json.loads(a.information.read_text())["tracks"]
    clean = [r["segment"] for r in rows if r["training_rms_hz"] <= 100 and r["span_s"] >= 15]
    for selection, mask in [("all", None), ("clean", np.isin(d["segment"], clean))]:
        for clock in [False, True]:
            result = fit(
                d,
                Region(**parent["region"]),
                parent["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=clock,
            )
            output["models"].append(dict(selection=selection, **result))
            print(selection, clock, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(a.output, output)


if __name__ == "__main__":
    main()
