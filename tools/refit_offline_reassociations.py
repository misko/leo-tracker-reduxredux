"""Refit the unchanged wide-search cohort with offline reassociated orbits."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, state_arrays, write_json
from replay_wide_alternative_tles import shared_clock_bounds
from replay_wide_session_clocks import recorded_clock_bounds

from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def bind_rows(assignments, rows):
    lookup = {(r["session_id"], r["episode_id"]): r for r in rows}
    if len(lookup) != len(rows) or set(lookup) != {
        (r["session_id"], r["episode_id"]) for r in assignments
    }:
        raise ValueError("reassociation coverage mismatch")
    ordered = [lookup[(a["session_id"], a["episode_id"])] for a in assignments]
    if any(a["norad"] != r["norad"] for a, r in zip(assignments, ordered, strict=True)):
        raise ValueError("original identity mismatch")
    return ordered


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["run", "rerank", "evidence", "timing-audit", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--verify-shared", action="store_true")
    a = p.parse_args()
    state_path = a.output.with_suffix(".npz")
    if a.output.exists() or state_path.exists():
        raise ValueError("fresh output required")
    parent = json.loads((a.run / "inference.json").read_text())
    rerank = json.loads(a.rerank.read_text())
    if rerank["parent_digest"] != digest(a.run / "inference.json") or not rerank["all_tracks"]:
        raise ValueError("complete matching parent required")
    rows = bind_rows(parent["assignments"], rerank["rows"])
    data = dict(np.load(a.run / "states.npz"))
    bounds = recorded_clock_bounds(
        data, parent["assignments"], json.loads(a.timing_audit.read_text()), a.evidence
    )
    for i, row in enumerate(rows):
        if row["best_norad"] is None:
            raise ValueError("unassigned episode: cannot silently remove")
        mask = data["episode"] == i
        doc = json.loads((a.evidence / "evidence" / (row["session_id"] + ".json")).read_text())
        arc = dict(load_observations(doc, 0))[row["episode_id"]]
        if not np.array_equal(arc.frequency_hz, data["y"][mask]) or not np.array_equal(
            arc.training, data["training"][mask]
        ):
            raise ValueError("RF evidence or partition mismatch")
        cat = parse_element_sets(row["winning_tle_text"])
        if cat.satellite_numbers != (row["best_norad"],):
            raise ValueError("winning orbit identity mismatch")
        if rerank.get("strictly_causal"):
            capture = doc["inventory"]["reference_utc_ns"]
            if row["capture_start_utc_ns"] != capture or not (
                row["winning_collected_utc_ns"] < capture
                and cat.element_epoch_utc_ns()[0] == row["winning_epoch_utc_ns"] < capture
            ):
                raise ValueError("noncausal winning orbit")
        for shift in [0.0, -0.5, 0.5]:
            pp, vv, valid = state_arrays(
                cat, [0], doc["inventory"]["reference_utc_ns"], arc.time_s, clock_s=shift
            )
            if len(valid) != 1:
                raise ValueError("invalid winning orbit")
            suffix = "" if shift == 0 else str(shift)
            data["p" + suffix][mask], data["v" + suffix][mask] = pp[0], vv[0]
        data["norad"][mask] = row["best_norad"]
    ids = [i for i, r in enumerate(parent["assignments"]) if r in parent["selected_assignments"]]
    out = dict(
        offline_noncausal=rerank["offline_noncausal"],
        strictly_causal=rerank.get("strictly_causal", False),
        evaluation_location_used=False,
        parent_digest=digest(a.run / "inference.json"),
        rerank_digest=digest(a.rerank),
        timing_digest=digest(a.timing_audit),
        models=[],
        changed_assignments=[r for r in rows if r["norad"] != r["best_norad"]],
    )
    for selection, mask in [
        ("all", np.ones(len(data["y"]), bool)),
        ("selected", np.isin(data["episode"], ids)),
    ]:
        for mode in ["fixed", "shared_recorded", "per_recording_recorded"]:
            result = fit(
                data,
                Region(**parent["region"]),
                parent["initial"],
                "observation",
                True,
                subset=mask,
                fit_clock=mode != "fixed",
                clock_groups=data["session"] if mode == "per_recording_recorded" else None,
                clock_bounds=None
                if mode == "fixed"
                else bounds
                if mode == "per_recording_recorded"
                else shared_clock_bounds(bounds, data["session"][mask]),
            )
            out["models"].append(dict(selection=selection, clock_model=mode, **result))
            print(selection, mode, result["latitude_deg"], result["longitude_deg"], flush=True)
            if a.verify_shared and mode == "shared_recorded":
                exact = {k: v.copy() for k, v in data.items()}
                for i, row in enumerate(rows):
                    episode_mask = data["episode"] == i
                    if not np.any(mask & episode_mask):
                        continue
                    doc = json.loads(
                        (a.evidence / "evidence" / (row["session_id"] + ".json")).read_text()
                    )
                    arc = dict(load_observations(doc, 0))[row["episode_id"]]
                    pp, vv, valid = state_arrays(
                        parse_element_sets(row["winning_tle_text"]),
                        [0],
                        doc["inventory"]["reference_utc_ns"],
                        arc.time_s,
                        clock_s=result["clock_s"],
                    )
                    if len(valid) != 1:
                        raise ValueError("invalid exact winning orbit")
                    exact["p"][episode_mask], exact["v"][episode_mask] = pp[0], vv[0]
                out["models"][-1]["exact_clock_refit"] = fit(
                    exact,
                    Region(**parent["region"]),
                    result["x_km"][:2],
                    "observation",
                    True,
                    subset=mask,
                )
                for grouping in ["norad", "session"]:
                    for fold in range(8):
                        retained = mask & (data[grouping] % 8 != fold)
                        check = fit(
                            data,
                            Region(**parent["region"]),
                            parent["initial"],
                            "observation",
                            True,
                            subset=retained,
                            fit_clock=True,
                            clock_bounds=shared_clock_bounds(bounds, data["session"][retained]),
                        )
                        out.setdefault("stability", []).append(
                            dict(selection=selection, grouping=grouping, fold=fold, **check)
                        )
                print(selection, "verification complete", flush=True)
    np.savez_compressed(state_path, **data)
    out["states_digest"] = digest(state_path)
    write_json(a.output, out)


if __name__ == "__main__":
    main()
