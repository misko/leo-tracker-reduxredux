"""Refine a completed randomized wide-search mode without any location reference.

Freeze training-selected identities, fit position/UTC, and verify with exact
SGP4 propagation. The selection policy was specified before the fresh wide run:
15-second episodes, 100 Hz training RMS, longest episode per satellite/session.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import extract, fit
from polish_regional_doppler import training_episode_gate
from replay_position_selection import selections
from replay_regional_doppler import digest, write_json

from leo.analysis.research.regional_doppler import Region


def freeze_assignments(run, evidence):
    parent = json.loads((run / "result.json").read_text())
    if (
        not parent["complete"]
        or parent["position_truth_used"]
        or parent["prior_matched_norads_used"]
        or parent.get("partition") != "randomized"
    ):
        raise ValueError("completed randomized RF-only parent required")
    if parent["altitude_m"] != 0:
        raise ValueError("this replay requires a zero-altitude parent")
    if parent.get("individual_sources", False):
        raise ValueError("episode-based parent required")
    history = json.loads((run / "history.json").read_text())
    if len(history) != parent["scan_count"]:
        raise ValueError("incomplete parent history")
    index = parent["best_index"]
    assignments, sources = [], {}
    for scan in history:
        path = evidence / "evidence" / (scan["session_id"] + ".json")
        if digest(path) != scan["source_digest"]:
            raise ValueError("RF evidence changed since search")
        doc = json.loads(path.read_text())
        meta = doc["inventory"]
        if meta.get("partition") != "randomized":
            raise ValueError("source partitions must be randomized")
        tle = path.parent / meta["tle_file"]
        if digest(tle) != scan["tle_digest"] or digest(tle) != meta["tle_digest"]:
            raise ValueError("TLE evidence changed since search")
        saved_path = run / (scan["session_id"] + ".npz")
        with np.load(saved_path) as saved:
            keep = training_episode_gate(
                saved["signal_weight"][:, index], saved["best_train_rms_hz"][:, index], 0.95, 500
            )
            if len(keep) != len(scan["episodes"]):
                raise ValueError("episode score/history mismatch")
            for j, episode in enumerate(scan["episodes"]):
                if keep[j]:
                    assignments.append(
                        dict(
                            session_id=scan["session_id"],
                            episode_id=episode["episode_id"],
                            norad=int(saved["best_norad"][j, index]),
                        )
                    )
        sources[str(saved_path)] = digest(saved_path)
    for name in ["result.json", "history.json", "accumulated.npz", "grid.npz"]:
        sources[str(run / name)] = digest(run / name)
    if len({r["norad"] for r in assignments}) < 3:
        raise ValueError("fewer than three selected satellite identities")
    return parent, assignments, sources


def polish(run, evidence, output):
    if output.exists():
        raise ValueError("fresh output required")
    parent, assignments, sources = freeze_assignments(run, evidence)
    data, provenance = extract(evidence, assignments)
    output.mkdir(parents=True)
    np.savez_compressed(output / "states.npz", **data)
    write_json(output / "inputs.json", dict(**provenance, parent_sources=sources))
    region = Region(**parent["region"])
    initial = [parent["east_km"], parent["north_km"]]
    baseline = fit(data, region, initial, "observation", True)
    ids = selections(data, baseline["segment_training_rms"])["rms100-longest-per-satellite"]
    if len(ids) < 3:
        raise ValueError("insufficient episodes passing the predeclared refinement selection")
    selected = [assignments[i] for i in ids]
    if len({r["norad"] for r in selected}) < 3:
        raise ValueError("insufficient independent satellite identities after selection")
    mask = np.isin(data["episode"], ids)
    models = []
    for label, subset, clock in [
        ("all-fixed-clock", None, False),
        ("all-shared-clock", None, True),
        ("selected-fixed-clock", mask, False),
        ("selected-shared-clock", mask, True),
    ]:
        row = (
            baseline
            if label == "all-fixed-clock"
            else fit(data, region, initial, "observation", True, subset=subset, fit_clock=clock)
        )
        models.append(dict(label=label, **row))
        print(label, row["latitude_deg"], row["longitude_deg"], row["clock_s"], flush=True)
    candidate = models[-1]
    exact, exact_provenance = extract(evidence, selected, clock_s=candidate["clock_s"])
    check = fit(exact, region, candidate["x_km"][:2], "observation", True)
    write_json(output / "exact-inputs.json", exact_provenance)
    folds = []
    for fold in range(8):
        use = mask & (data["norad"] % 8 != fold)
        if len(np.unique(data["norad"][use])) < 3:
            continue
        row = fit(data, region, initial, "observation", True, subset=use, fit_clock=True)
        folds.append(dict(excluded_norad_mod8=fold, **row))
    write_json(
        output / "inference.json",
        dict(
            complete=True,
            position_truth_used=False,
            prior_matched_norads_used=False,
            partition="randomized",
            parent_run=str(run),
            parent_sources=sources,
            region=parent["region"],
            initial=initial,
            assignments=assignments,
            selected_assignments=selected,
            models=models,
            exact_clock_refit=check,
            exact_propagation_clock_s=candidate["clock_s"],
            leave_satellite_fold_out=folds,
            selection=dict(
                minimum_span_s=15,
                maximum_training_rms_hz=100,
                longest_per_satellite_and_session=True,
            ),
            selection_is_exploratory=True,
            inherits_global_provenance_from_parent=True,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run", "evidence", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    polish(args.run, args.evidence, args.output)


if __name__ == "__main__":
    main()
