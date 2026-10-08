"""Frozen joint-wide replication after distinct-region rescue."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REGIONS = HERE.parent / "2026_10_08_position_error_iter06"
JOINT = HERE.parent / "2026_10_08_position_error_iter04"
for directory in (
    REGIONS,
    JOINT,
    HERE.parent / "2026_10_08_position_error_iter01",
    HERE.parent / "2026_10_08_hard60_bounded_recovery",
):
    sys.path.insert(0, str(directory))
from baseline import load_case  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from joint_clock import JointClockObjective, fit  # noqa: E402
from newer_inputs import load_newer  # noqa: E402
from probe import error_km  # noqa: E402
from leo.analysis.hard60_bounded_fit import fit_bounded_position  # noqa: E402
from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def run(label, protocol):
    assert label in protocol["labels"]
    assert (
        hashlib.sha256((JOINT / "joint_clock.py").read_bytes()).hexdigest()
        == protocol["joint_sha256"]
    )
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    case = load_newer(label) if label.startswith("NEW-") else load_case(label)
    document = (
        case.document
        if label.startswith("NEW-")
        else json.loads((REGIONS / "results" / label / "separation-25.json").read_text())
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    start = next(
        r
        for r in document["diagnostics"]["final_starts"]
        if r["arm"] == "fitted-c"
        and r["basin"] == selected["source_basin"]
        and r["fit"]
        and r["fit"]["converged"]
        and abs(r["fit"]["objective"] - selected["objective"]) < 1e-9
    )
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in selected["satellites"]])
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    seed = np.asarray(start["fit"]["vector"])
    correction = calibration["correction"]
    model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2.0)
    results = []
    for variant in ("matched-control", "joint-wide"):
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
            else:
                result = json_value(fit(model, seed, arm=arm))
            result.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, result["vector"], document)
            )
            results.append(result)
            print(label, variant, arm, result["converged"], result["error_km"], flush=True)
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            seed=seed,
            source_basin=selected["source_basin"],
            satellites=bank.numbers.tolist(),
            input_manifest_sha256=document["input_manifest_sha256"],
            analysis_manifest_sha256=document["analysis_manifest_sha256"],
            baseline_arms=document["methods"][0]["arms"],
            candidates=results,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, protocol)
