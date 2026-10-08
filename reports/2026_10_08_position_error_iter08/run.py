"""Matched sensitivity to smooth-clock regularization on consumed development data."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
JOINT = HERE.parent / "2026_10_08_position_error_iter04"
for directory in (
    JOINT,
    HERE.parent / "2026_10_08_position_error_iter01",
    HERE.parent / "2026_10_08_hard60_bounded_recovery",
    HERE.parent / "2026_10_08_position_error_iter06",
):
    sys.path.insert(0, str(directory))
from baseline import load_case  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from joint_clock import JointClockObjective, fit  # noqa: E402
from newer_inputs import load_newer  # noqa: E402
from probe import error_km, load  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def basis(label):
    if not label.startswith("NEW-") and label != "DS17-008":
        return load(label)
    case = load_newer(label) if label.startswith("NEW-") else load_case(label)
    document = (
        case.document
        if label.startswith("NEW-")
        else json.loads(
            (
                HERE.parent / "2026_10_08_position_error_iter06/results/DS17-008/separation-25.json"
            ).read_text()
        )
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    row = next(
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
    return case, document, base, np.asarray(row["fit"]["vector"])


def run(label, protocol):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    case, document, base, seed = basis(label)
    source = (
        HERE.parent / "2026_10_08_position_error_iter07/results"
        if label.startswith("NEW-") or label == "DS17-008"
        else JOINT / "probes"
    ) / f"{label}.json"
    previous = json.loads(source.read_text())
    np.testing.assert_array_equal(seed, previous["seed"])
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    rows = []
    for variant, scale in protocol["variants"].items():
        model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], scale)
        for arm in ("fitted-c", "zero-c"):
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
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            satellites=base.bank.numbers.tolist(),
            baseline_arms=[
                dict(name=a["name"], selected=a["selected"]) for a in document["methods"][0]["arms"]
            ],
            previous_candidates=[
                r
                for r in previous["candidates"]
                if r["variant"] in ("matched-control", "joint-wide")
            ],
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert (
        hashlib.sha256((JOINT / "joint_clock.py").read_bytes()).hexdigest()
        == protocol["joint_sha256"]
    )
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == protocol["runner_sha256"]
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, protocol)
