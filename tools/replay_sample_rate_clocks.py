"""Test whether acquisition-rate UTC biases explain the current position bias."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["states", "inference", "information", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    d = dict(np.load(a.states))
    d["p"], d["v"], d["episode"] = d["p0.0"], d["v0.0"], d["segment"]
    parent = json.loads(a.inference.read_text())
    cohort = parent["cohorts"]["current_fov_selected"]
    region = Region(**cohort["region"])
    rows = json.loads(a.information.read_text())["tracks"]
    ids = [r["segment"] for r in rows if r["training_rms_hz"] <= 100 and r["span_s"] >= 15]
    out = dict(
        source_digests={str(path): digest(path) for path in [a.states, a.inference, a.information]},
        evaluation_location_used=False,
        identity_provenance=parent["identity_provenance"]["current_fov_selected"],
        partition="randomized",
        clock_bound_s=0.5,
        models=[],
    )
    for subset, mask in [("all", None), ("clean", np.isin(d["segment"], ids))]:
        for grouping in ["shared", "sample-rate"]:
            row = fit(
                d,
                region,
                cohort["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=True,
                clock_groups=d["rate"] if grouping == "sample-rate" else None,
            )
            out["models"].append(dict(subset=subset, grouping=grouping, **row))
            print(
                subset,
                grouping,
                row["latitude_deg"],
                row["longitude_deg"],
                row["clock_offsets_s"],
                flush=True,
            )
    write_json(a.output, out)


if __name__ == "__main__":
    main()
