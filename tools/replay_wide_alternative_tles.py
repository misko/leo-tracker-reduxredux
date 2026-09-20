"""Offline orbit sensitivity with frozen independent-wide IDs and RF evidence."""

import argparse
import json
from pathlib import Path

import numpy as np
from compare_positioning_cohorts import fit
from replay_regional_doppler import digest, load_observations, state_arrays, write_json
from replay_wide_session_clocks import recorded_clock_bounds

from leo.analysis.research.regional_doppler import Region
from leo.sky.propagation import parse_element_sets


def validate_assignment_order(assignments, rows):
    def keys(r):
        return r["session_id"], r["episode_id"], r["norad"]

    if [keys(a) for a in assignments] != [keys(r) for r in rows]:
        raise ValueError("audit assignment order or identity differs")


def shared_clock_bounds(bounds, groups):
    intervals = np.asarray([bounds[int(g)] for g in np.unique(groups)])
    lower, upper = float(intervals[:, 0].max()), float(intervals[:, 1].min())
    if not np.isfinite([lower, upper]).all() or lower >= upper:
        raise ValueError("recorded clocks have no shared interval")
    return {0: (lower, upper)}


def blend_states(p0, v0, p1, v1, elapsed_s, interval_s):
    """Interpolate propagated states, including derivative of the time weight."""
    if not np.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("positive epoch interval required")
    fraction = np.asarray(elapsed_s) / interval_s
    weight = np.clip(fraction, 0, 1)[:, None]
    derivative = ((fraction > 0) & (fraction < 1))[:, None] / interval_s
    return (
        (1 - weight) * p0 + weight * p1,
        (1 - weight) * v0 + weight * v1 + derivative * (p1 - p0),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["run", "audit", "evidence", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument(
        "--epoch-side",
        choices=["nearest", "preceding", "succeeding", "interpolated"],
        default="nearest",
    )
    parser.add_argument("--timing-audit", type=Path)
    parser.add_argument("--verify-shared", action="store_true")
    args = parser.parse_args()
    if args.verify_shared and (args.epoch_side != "nearest" or not args.timing_audit):
        raise ValueError("shared verification requires nearest orbits and recorded timing")
    if args.output.exists():
        raise ValueError("fresh output required")
    parent_path = args.run / "inference.json"
    parent = json.loads(parent_path.read_text())
    audit = json.loads(args.audit.read_text())
    if args.epoch_side != "nearest" and not audit["offline_noncausal"]:
        raise ValueError("epoch-side replay requires explicit offline audit")
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
    bounds = (
        recorded_clock_bounds(
            data, parent["assignments"], json.loads(args.timing_audit.read_text()), args.evidence
        )
        if args.timing_audit
        else None
    )
    out = dict(
        evaluation_location_used=False,
        offline_noncausal=audit["offline_noncausal"],
        parent_digest=digest(parent_path),
        audit_digest=digest(args.audit),
        states_digest=digest(args.run / "states.npz"),
        timing_audit_digest=digest(args.timing_audit) if args.timing_audit else None,
        invalid_replacements=[],
        unavailable_replacements=[],
        interpolation_fallback_to_nearest=[],
        epoch_side=args.epoch_side,
        models=[],
    )
    differences = []
    for i, row in enumerate(audit["rows"]):
        selected = (
            row["selected"]
            if args.epoch_side in {"nearest", "interpolated"}
            else row["offline_bracket"][args.epoch_side]
        )
        if selected is None:
            out["unavailable_replacements"].append(i)
            continue
        mask = data["episode"] == i
        doc = json.loads((args.evidence / "evidence" / (row["session_id"] + ".json")).read_text())
        arc = dict(load_observations(doc, 0))[row["episode_id"]]
        if not np.array_equal(arc.frequency_hz, data["y"][mask]) or not np.array_equal(
            arc.training, data["training"][mask]
        ):
            raise ValueError("RF evidence/partition mismatch")
        if row["measurement_utc_ns"] != doc["inventory"]["reference_utc_ns"]:
            raise ValueError("measurement UTC mismatch")
        cat = parse_element_sets(selected["text"])
        if cat.satellite_numbers != (row["norad"],):
            raise ValueError("replacement NORAD differs")
        pair = None
        if args.epoch_side == "interpolated":
            before, after = (row["offline_bracket"][key] for key in ["preceding", "succeeding"])
            if (
                before is not None
                and after is not None
                and after["epoch_utc_ns"] > before["epoch_utc_ns"]
            ):
                pair = [parse_element_sets(x["text"]) for x in [before, after]]
                if any(c.satellite_numbers != (row["norad"],) for c in pair):
                    raise ValueError("interpolated NORAD differs")
            else:
                out["interpolation_fallback_to_nearest"].append(i)
        replacements = {}
        for shift in [0.0, -0.5, 0.5]:
            p, v, valid = state_arrays(
                cat, [0], row["measurement_utc_ns"], arc.time_s, clock_s=shift
            )
            if len(valid) != 1:
                break
            if pair is not None:
                left = state_arrays(
                    pair[0], [0], row["measurement_utc_ns"], arc.time_s, clock_s=shift
                )
                right = state_arrays(
                    pair[1], [0], row["measurement_utc_ns"], arc.time_s, clock_s=shift
                )
                if len(left[2]) != 1 or len(right[2]) != 1:
                    break
                elapsed = (
                    (row["measurement_utc_ns"] - before["epoch_utc_ns"]) / 1e9 + arc.time_s + shift
                )
                interval = (after["epoch_utc_ns"] - before["epoch_utc_ns"]) / 1e9
                pp, vv = blend_states(
                    left[0][0], left[1][0], right[0][0], right[1][0], elapsed, interval
                )
                p, v = pp[None], vv[None]
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
        if bounds is not None:
            selected = np.ones(len(data["y"]), bool) if mask is None else mask
            for mode in ["shared_recorded", "per_recording_recorded"]:
                result = fit(
                    data,
                    Region(**parent["region"]),
                    parent["initial"],
                    "observation",
                    True,
                    subset=mask,
                    fit_clock=True,
                    clock_groups=data["session"] if mode == "per_recording_recorded" else None,
                    clock_bounds=bounds
                    if mode == "per_recording_recorded"
                    else shared_clock_bounds(bounds, data["session"][selected]),
                )
                out["models"].append(dict(selection=selection, clock_model=mode, **result))
                print(selection, mode, result["latitude_deg"], result["longitude_deg"], flush=True)
                if args.verify_shared and mode == "shared_recorded":
                    if out["invalid_replacements"] or out["unavailable_replacements"]:
                        raise ValueError("exact verification requires all replacements valid")
                    exact = {k: v.copy() for k, v in data.items()}
                    for i, row in enumerate(audit["rows"]):
                        episode_mask = data["episode"] == i
                        if not np.any(selected & episode_mask):
                            continue
                        doc = json.loads(
                            (args.evidence / "evidence" / (row["session_id"] + ".json")).read_text()
                        )
                        arc = dict(load_observations(doc, 0))[row["episode_id"]]
                        p, v, valid = state_arrays(
                            parse_element_sets(row["selected"]["text"]),
                            [0],
                            row["measurement_utc_ns"],
                            arc.time_s,
                            clock_s=result["clock_s"],
                        )
                        if len(valid) != 1:
                            raise ValueError("exact orbit propagation failed")
                        exact["p"][episode_mask], exact["v"][episode_mask] = p[0], v[0]
                    result["exact_clock_refit"] = fit(
                        exact,
                        Region(**parent["region"]),
                        result["x_km"][:2],
                        "observation",
                        True,
                        subset=mask,
                    )
                    # The model entry was copied before adding the nested verification.
                    out["models"][-1]["exact_clock_refit"] = result["exact_clock_refit"]
                    for grouping in ["norad", "session"]:
                        for fold in range(8):
                            retained = selected & (data[grouping] % 8 != fold)
                            replay = fit(
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
                                dict(
                                    selection=selection,
                                    grouping=grouping,
                                    fold=fold,
                                    **replay,
                                )
                            )
                    print(selection, "verification complete", flush=True)
    write_json(args.output, out)


if __name__ == "__main__":
    main()
