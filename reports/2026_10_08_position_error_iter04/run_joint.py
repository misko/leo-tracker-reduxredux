"""Controlled local clock/position fits; DS17 validation remains locked."""

import sys
from pathlib import Path

from joint_clock import VARIANTS, JointClockObjective, fit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter01"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from inputs import json_value, write_json  # noqa: E402
from probe import error_km, load  # noqa: E402

from leo.analysis.hard60_bounded_fit import fit_bounded_position  # noqa: E402


def run(label, variants=("matched-control", *VARIANTS)):
    output = HERE / "probes" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    case, document, base, seed = load(label)
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    rows = []
    for variant in variants:
        model = JointClockObjective(
            base, calibration["nodes_s"], calibration["knots_hz"], VARIANTS.get(variant, 1.0)
        )
        for arm in ("fitted-c", "zero-c"):
            if variant == "matched-control":
                result, _ = fit_bounded_position(
                    base,
                    seed,
                    rf_arm=arm,
                    maximum_seconds=20,
                    maximum_iterations=600,
                    local_center=seed[:2],
                    local_radius_km=25,
                )
                result = json_value(result)
                penalty = float(0.5 * model.initial_clock @ model.precision @ model.initial_clock)
                result["calibration_penalty"] = penalty
                result["objective"] += penalty
                result["knots_hz"] = calibration["knots_hz"]
            else:
                result = json_value(fit(model, seed, arm=arm))
            result.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, result["vector"], document)
            )
            rows.append(result)
            print(
                label, variant, arm, result["converged"], round(result["error_km"], 4), flush=True
            )
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            seed=seed,
            satellites=base.bank.numbers.tolist(),
            calibration=calibration,
            observation_count=len(base.observations.window_ids),
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
