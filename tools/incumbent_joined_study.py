"""Matched anchored continuation versus same-objective parent-state transport."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import (
    ARMS,
    LOCAL,
    PREVIOUS,
    REPORT,
    ROOT,
    VARIANTS,
    load_inputs,
    restore,
)
from continuous_merge_study import plain, sha, write

from leo.analysis.anchored_joint_fit import fit_anchored_joint
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

DESTINATION = REPORT / "local/incumbent-joined"
CALIBRATIONS = ("zero", "cal")
STARTS = ("continue", "incumbent")


def freeze():
    output = DESTINATION / "protocol.json"
    if output.exists():
        raise ValueError("incumbent study already frozen")
    selection_path = PREVIOUS / "cohort-selection.json"
    selection = json.loads(selection_path.read_bytes())
    paths, cases = [selection_path, Path(__file__)], []
    paths += sorted((ROOT / "src/leo/analysis").glob("*.py"))
    paths += sorted((ROOT / "src/leo/application").glob("*.py"))
    paths += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    paths += [
        ROOT / "tools/band_calibrated_merge_study.py",
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    for member in selection["members"]:
        case = LOCAL / member["dataset"] / member["session_id"]
        parent_protocol_path = case / "protocol.json"
        parent = json.loads(parent_protocol_path.read_bytes())
        for path, digest in parent["bindings"].items():
            if sha(Path(path)) != digest:
                raise ValueError("parent authority changed: " + path)
        paths += [Path(p) for p in parent["bindings"]]
        paths.append(parent_protocol_path)
        prepared, bank, final = load_inputs(Path(parent["parent_case"]))
        entries = []
        for calibration in CALIBRATIONS:
            variant = calibration + "-joined"
            model, _, _ = restore(
                prepared, bank, final, parent["groups"]["joined"], VARIANTS[variant]
            )
            for arm in ARMS:
                scores = {}
                for grouping in ("parents", "joined"):
                    path = case / (calibration + "-" + grouping + "-" + arm + ".json")
                    result = json.loads(path.read_bytes())
                    if not result["fit"]["converged"]:
                        raise ValueError("this panel requires stationary saved source fits")
                    vector = np.array(result["fit"]["vector"])
                    clock = np.array(result["fit"]["clock_coefficients"])
                    if np.linalg.norm(vector[:2] - final["fit"]["vector"][:2]) > 25.0 + 1e-7:
                        raise ValueError("candidate lies outside original local disk")
                    if arm == "zero-c" and (
                        abs(vector[6]) > 1e-8 or np.max(np.abs(clock[-2:])) > 1e-8
                    ):
                        raise ValueError("source candidate violated c locks")
                    scores[grouping] = float(model.evaluate_joint(vector, clock)[0])
                    paths.append(path)
                if (
                    abs(
                        scores["joined"]
                        - json.loads((case / (variant + "-" + arm + ".json")).read_bytes())[
                            "objective"
                        ]
                    )
                    > 1e-6
                ):
                    raise ValueError("joined source score did not reproduce")
                chosen = "parents" if scores["parents"] < scores["joined"] - 1e-6 else "joined"
                entries.append(
                    {
                        "calibration": calibration,
                        "arm": arm,
                        "candidate_objectives": scores,
                        "chosen_source": chosen,
                    }
                )
        cases.append(
            {
                "dataset": member["dataset"],
                "session_id": member["session_id"],
                "role": member["role"],
                "parent_case": str(case),
                "local_center_km": final["fit"]["vector"][:2],
                "satellites": final["satellites"],
                "entries": entries,
            }
        )
    write(
        output,
        {
            "cases": cases,
            "starts": STARTS,
            "calibrations": CALIBRATIONS,
            "arms": ARMS,
            "bindings": {str(path): sha(path) for path in paths},
            "maximum_seconds": 90,
            "maximum_iterations": 600,
            "local_radius_km": 25.0,
            "reference_usage": "none in freeze or execute",
            "scope": (
                "Same joined model, bank, observations, priors and original 25 km disk; "
                "continue from saved joined state versus lowest-score feasible parent/joined "
                "source. "
                "Each branch gets one additional 90 s/600-iteration fit; saved source states are "
                "common preprocessing. The qualified original joined fit remains fallback if "
                "refinement is nonstationary or has a worse joined objective. No reference used."
            ),
        },
    )
    print(
        json.dumps(
            {
                "cases": len(cases),
                "fits": 64,
                "parent_starts": sum(
                    e["chosen_source"] == "parents" for c in cases for e in c["entries"]
                ),
            }
        )
    )


def verify(protocol):
    for path, digest in protocol["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("incumbent study authority changed: " + path)


def execute(dataset, sid, calibration, arm, start):
    protocol_path = DESTINATION / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    entry = next(c for c in protocol["cases"] if c["dataset"] == dataset and c["session_id"] == sid)
    point = next(e for e in entry["entries"] if e["calibration"] == calibration and e["arm"] == arm)
    path = DESTINATION / dataset / sid / (calibration + "-" + arm + "-" + start + ".json")
    if path.exists():
        print("already recorded")
        return
    parent_case = Path(entry["parent_case"])
    parent = json.loads((parent_case / "protocol.json").read_bytes())
    prepared, bank, final = load_inputs(Path(parent["parent_case"]))
    model, _, _ = restore(
        prepared, bank, final, parent["groups"]["joined"], VARIANTS[calibration + "-joined"]
    )
    source = point["chosen_source"] if start == "incumbent" else "joined"
    original = json.loads((parent_case / (calibration + "-joined-" + arm + ".json")).read_bytes())
    chosen = json.loads(
        (parent_case / (calibration + "-" + source + "-" + arm + ".json")).read_bytes()
    )
    attempt = fit_anchored_joint(
        model,
        np.array(chosen["fit"]["vector"]),
        arm=arm,
        local_center=entry["local_center_km"],
        local_radius_km=protocol["local_radius_km"],
        clock_seed=np.array(chosen["fit"]["clock_coefficients"]),
        maximum_seconds=protocol["maximum_seconds"],
        maximum_iterations=protocol["maximum_iterations"],
    )
    accepted = attempt["converged"] and attempt["objective"] <= original["objective"] + 1e-6
    selected = attempt if accepted else original["fit"]
    vector, clock = np.array(selected["vector"]), np.array(selected["clock_coefficients"])
    value, _, _, terms = model.evaluate_joint(vector, clock)
    if value > original["objective"] + 1e-6:
        raise ValueError("qualified incumbent objective was lost")
    write(
        path,
        {
            "dataset": dataset,
            "session_id": sid,
            "calibration": calibration,
            "arm": arm,
            "start": start,
            "source": source,
            "attempt": plain(attempt),
            "accepted": accepted,
            "fit": plain(selected),
            "objective": float(value),
            "original_joined_objective": original["objective"],
            "mark_nll": terms.nll,
            "band_offsets_hz": model.band_offsets_hz(clock),
            "protocol_sha256": sha(protocol_path),
            "reference_usage": "none",
        },
    )
    print(
        json.dumps(
            {
                "session_id": sid,
                "calibration": calibration,
                "arm": arm,
                "start": start,
                "source": source,
                "stationary": attempt["converged"],
                "accepted": accepted,
                "objective_gain": original["objective"] - value,
            }
        ),
        flush=True,
    )


def evaluate():
    protocol_path = DESTINATION / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    paths = [
        DESTINATION / c["dataset"] / c["session_id"] / (cal + "-" + arm + "-" + s + ".json")
        for c in protocol["cases"]
        for cal in CALIBRATIONS
        for arm in ARMS
        for s in STARTS
    ]
    results = [json.loads(p.read_bytes()) for p in paths]
    seal = {str(p): sha(p) for p in paths}
    seal_path = DESTINATION / "evaluation-seal.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("incumbent evaluation changed")
    write(seal_path, seal)
    references = {}
    for c in protocol["cases"]:
        source_case = Path(c["parent_case"])
        p = source_case / "evaluation-cohort-reference.json"
        if p.exists():
            reference = json.loads(p.read_bytes())["reference"]
        else:
            position = (
                Path(json.loads((source_case / "protocol.json").read_bytes())["parent_case"])
                / "positions"
            )
            p = next(position.glob("evaluation-baseline-*.json"))
            reference = json.loads(p.read_bytes())["reference"]
        references[c["session_id"]] = {"path": str(p), "sha256": sha(p), "reference": reference}
    rows = []
    for result in results:
        reference = references[result["session_id"]]["reference"]
        lat, lon, rlat, rlon = map(
            math.radians, (*coordinates(RegionalPrior(), result["fit"]["vector"][:2]), *reference)
        )
        h = (
            math.sin((lat - rlat) / 2) ** 2
            + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
        )
        rows.append(
            {
                **{
                    k: result[k]
                    for k in (
                        "dataset",
                        "session_id",
                        "calibration",
                        "arm",
                        "start",
                        "source",
                        "accepted",
                        "objective",
                        "original_joined_objective",
                    )
                },
                "reference_error_m": 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h)))),
                "attempt_stationary": result["attempt"]["converged"],
                "selected_stationary": result["fit"]["converged"],
            }
        )
    write(
        DESTINATION / "evaluation.json",
        {
            "rows": rows,
            "references": references,
            "seal_sha256": sha(seal_path),
            "protocol_sha256": sha(protocol_path),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "evaluate"))
    parser.add_argument("dataset", nargs="?", choices=("DS20", "DS16"))
    parser.add_argument("session_id", nargs="?")
    parser.add_argument("--calibration", choices=CALIBRATIONS, default="cal")
    parser.add_argument("--arm", choices=ARMS, default="fitted-c")
    parser.add_argument("--start", choices=STARTS, default="incumbent")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze()
    elif args.command == "evaluate":
        evaluate()
    else:
        execute(args.dataset, args.session_id, args.calibration, args.arm, args.start)
