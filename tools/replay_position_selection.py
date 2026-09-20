"""Predeclared training-only selection ablations of frozen wide-search identities.

No antenna reference is read. Report every variant; none is selected by location error.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import extract, fit
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def selections(data, segment_rms):
    episodes = []
    for episode in np.unique(data["episode"]):
        mask = data["episode"] == episode
        fitting = mask & data["training"]
        rms = np.sqrt(np.mean([segment_rms[str(s)] ** 2 for s in data["segment"][fitting]]))
        episodes.append(
            dict(
                id=int(episode),
                key=(int(data["session"][mask][0]), int(data["norad"][mask][0])),
                span=float(np.ptp(data["time"][mask])),
                rms=float(rms),
            )
        )
    out = {}
    for cap in [100.0, 200.0, 500.0]:
        for deduplicate in [False, True]:
            chosen = [r for r in episodes if r["span"] >= 15 and r["rms"] <= cap]
            if deduplicate:
                groups = {}
                for row in chosen:
                    if row["key"] not in groups or row["span"] > groups[row["key"]]["span"]:
                        groups[row["key"]] = row
                chosen = list(groups.values())
            name = f"rms{int(cap)}-" + ("longest-per-satellite" if deduplicate else "all")
            out[name] = [r["id"] for r in chosen]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exact-source", type=Path)
    a = parser.parse_args()
    parent = json.loads((a.run / "results.json").read_text())
    name = "historical_wide_selected"
    cohort = parent["cohorts"][name]
    data = dict(np.load(a.run / (name + ".npz")))
    nominal = next(
        r
        for r in cohort["models"]
        if r["weighting"] == "observation" and r["robust"] and not r["clock_fitted"]
    )
    masks = selections(data, nominal["segment_training_rms"])
    results = {
        "parent_digest": digest(a.run / "results.json"),
        "truth_used": False,
        "identity_source": "historical broad-region training selection; not reselected",
        "models": [],
    }
    records = json.loads((a.run / (name + "-inputs.json")).read_text())["records"]
    for selection, ids in masks.items():
        mask = np.isin(data["episode"], ids)
        for clock in [False, True]:
            row = fit(
                data,
                Region(**cohort["region"]),
                cohort["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=clock,
            )
            if clock and a.exact_source:
                assignments = [
                    {k: records[i][k] for k in ["session_id", "episode_id", "norad"]} for i in ids
                ]
                exact, _ = extract(a.exact_source, assignments, clock_s=row["clock_s"])
                row["exact_refit"] = fit(
                    exact, Region(**cohort["region"]), row["x_km"][:2], "observation", True
                )
            results["models"].append(dict(selection=selection, episode_ids=ids, **row))
            print(
                selection,
                clock,
                len(ids),
                row["clock_s"],
                row["latitude_deg"],
                row["longitude_deg"],
                flush=True,
            )
    write_json(a.output, results)


if __name__ == "__main__":
    main()
