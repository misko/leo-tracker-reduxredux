"""Fixed remove-5 evaluation on the previously consumed DS17 validation cohort."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_10_08_position_error_iter10"
BASELINES = HERE.parent / "2026_10_08_position_error_iter01/baseline"
PREVIOUS = HERE.parent / "2026_10_08_position_error_iter05/results"
sys.path[:0] = [
    str(SOURCE),
    str(HERE.parent / "2026_10_08_position_error_iter01"),
    str(HERE.parent / "2026_10_08_hard60_bounded_recovery"),
]
from baseline import load_case  # noqa: E402
from experiment import reduce_bank  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
from timing_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def run(label):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    case = load_case(label)
    baseline_path = BASELINES / f"{label}.json"
    document = json.loads(baseline_path.read_text())
    source = PREVIOUS / f"{label}.json"
    previous = json.loads(source.read_text())
    assert hashlib.sha256(baseline_path.read_bytes()).hexdigest() == previous["baseline_sha256"]
    chosen = next(
        r for r in previous["candidates"] if r["variant"] == "joint-wide" and r["arm"] == "fitted-c"
    )
    assert chosen["converged"]
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
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
    correction = calibration["correction"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    model = JointClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)
    np.testing.assert_allclose(
        model.evaluate_joint(seed, clock)[0], chosen["objective"], atol=1e-6, rtol=0
    )
    rows = []
    for variant in ("warm-control", "remove-5"):
        subset, start, removed = base, seed, []
        if variant == "remove-5":
            subset, start, removed = reduce_bank(base, seed, 5)
        model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], 2)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, start, arm=arm, clock_seed=clock))
            row.update(
                variant=variant,
                arm=arm,
                removed=removed,
                satellites=subset.bank.numbers.tolist(),
                error_km=error_km(case.prior, row["vector"], document),
            )
            rows.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 4), flush=True)
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            prior_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            baseline_sha256=previous["baseline_sha256"],
            seed=seed,
            baseline_arms=[
                dict(name=a["name"], selected=a["selected"]) for a in document["methods"][0]["arms"]
            ],
            previous_candidates=previous["candidates"],
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == protocol["runner_sha256"]
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        if label == "DS17-008":
            path = SOURCE / "results/DS17-008.json"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == protocol["reused_rescue_sha256"]
            print(label, "reuse sealed rescued-region result", flush=True)
        else:
            run(label)
