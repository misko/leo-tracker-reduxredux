"""Compare pass-balanced position fits with frozen cohorts and identities."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "historical-run",
        "current-states",
        "current-parent",
        "current-information",
        "output",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    historical_parent = a.historical_run / "inference.json"
    historical_states = a.historical_run / "states.npz"
    parent = json.loads(historical_parent.read_text())
    h = dict(np.load(historical_states))
    _, h["pass_group"] = np.unique(
        np.column_stack([h["session"], h["norad"]]), axis=0, return_inverse=True
    )
    ids = [
        i for i, row in enumerate(parent["assignments"]) if row in parent["selected_assignments"]
    ]
    current = json.loads(a.current_parent.read_text())["cohorts"]["current_fov_selected"]
    d = dict(np.load(a.current_states))
    d["p"], d["v"], d["episode"] = d["p0.0"], d["v0.0"], d["segment"]
    rows = json.loads(a.current_information.read_text())["tracks"]
    clean = [r["segment"] for r in rows if r["training_rms_hz"] <= 100 and r["span_s"] >= 15]
    output = dict(
        evaluation_location_used=False,
        source_digests={
            str(p): digest(p)
            for p in [
                historical_parent,
                historical_states,
                a.current_parent,
                a.current_states,
                a.current_information,
            ]
        },
        historical_identity_provenance="independent wide-search fitting identities",
        current_identity_provenance="known-site FoV-assisted identities; conditional replay",
        weighting="equal total fitting weight per candidate satellite pass",
        historical_pass_definition="NORAD and recording pair",
        current_pass_definition="inherited pass_group from error-budget state bundle",
        models=[],
    )
    for label, data, cohort, mask in [
        ("historical-all", h, parent, None),
        ("historical-selected", h, parent, np.isin(h["episode"], ids)),
        ("current-all", d, current, None),
        ("current-selected", d, current, np.isin(d["segment"], clean)),
    ]:
        for clock in [False, True]:
            result = fit(
                data,
                Region(**cohort["region"]),
                cohort["initial"],
                "pass",
                True,
                subset=mask,
                fit_clock=clock,
            )
            result["candidate_pass_count"] = len(
                np.unique(data["pass_group"] if mask is None else data["pass_group"][mask])
            )
            output["models"].append(dict(cohort=label, **result))
            print(label, clock, result["latitude_deg"], result["longitude_deg"], flush=True)
    write_json(a.output, output)


if __name__ == "__main__":
    main()
