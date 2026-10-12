"""Compare joined fits with feasible parent-model states under the same objective."""

import json
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import (
    ARMS,
    LOCAL,
    PREVIOUS,
    REPORT,
    VARIANTS,
    load_inputs,
    restore,
)
from continuous_merge_study import sha, write


def main():
    selection_path = PREVIOUS / "cohort-selection.json"
    selection = json.loads(selection_path.read_bytes())
    rows, bindings = [], {str(selection_path): sha(selection_path)}
    for member in selection["members"]:
        case = LOCAL / member["dataset"] / member["session_id"]
        protocol_path = case / "protocol.json"
        protocol = json.loads(protocol_path.read_bytes())
        for path, digest in protocol["bindings"].items():
            if sha(Path(path)) != digest:
                raise ValueError("model authority changed: " + path)
        prepared, bank, final = load_inputs(Path(protocol["parent_case"]))
        bindings[str(protocol_path)] = sha(protocol_path)
        for calibration in ("zero", "cal"):
            joined_variant, parent_variant = calibration + "-joined", calibration + "-parents"
            model, _, _ = restore(
                prepared, bank, final, protocol["groups"]["joined"], VARIANTS[joined_variant]
            )
            for arm in ARMS:
                parent_path = case / (parent_variant + "-" + arm + ".json")
                joined_path = case / (joined_variant + "-" + arm + ".json")
                parent, joined = [json.loads(p.read_bytes()) for p in (parent_path, joined_path)]
                bindings.update({str(p): sha(p) for p in (parent_path, joined_path)})
                evaluations = []
                for candidate in (parent, joined):
                    vector = np.array(candidate["fit"]["vector"])
                    clock = np.array(candidate["fit"]["clock_coefficients"])
                    if arm == "zero-c" and (
                        abs(vector[6]) > 1e-8 or np.max(np.abs(clock[-2:])) > 1e-8
                    ):
                        raise ValueError("a feasible c=0 state violated its RF locks")
                    value, _, _, terms = model.evaluate_joint(vector, clock)
                    evaluations.append((float(value), float(terms.nll)))
                if abs(evaluations[1][0] - joined["objective"]) > 1e-6:
                    raise ValueError("saved joined objective did not reproduce")
                rows.append(
                    {
                        "dataset": member["dataset"],
                        "session_id": member["session_id"],
                        "calibration": calibration,
                        "arm": arm,
                        "joined_objective_at_parent_state": evaluations[0][0],
                        "joined_objective_at_joined_state": evaluations[1][0],
                        "parent_state_improvement": evaluations[1][0] - evaluations[0][0],
                        "parent_state_is_better": evaluations[0][0] < evaluations[1][0] - 1e-6,
                        "parent_stationary": parent["fit"]["converged"],
                        "joined_stationary": joined["fit"]["converged"],
                        "reference_usage": "none",
                    }
                )
    write(
        REPORT / "joined-parent-start-audit.json",
        {
            "rows": rows,
            "bindings": bindings,
            "script_sha256": sha(Path(__file__)),
            "scope": (
                "Same joined model, bank, observations, priors and feasible c locks for both "
                "candidate states; no geographic reference used."
            ),
        },
    )
    print(json.dumps([r for r in rows if r["parent_state_is_better"]], indent=2))


if __name__ == "__main__":
    main()
