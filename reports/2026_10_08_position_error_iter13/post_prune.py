"""Clock-prior interaction with a fixed, previously pruned candidate bank."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
SOURCE = REPORTS / "2026_10_08_position_error_iter10"
sys.path[:0] = [
    str(SOURCE),
    str(REPORTS / "2026_10_08_position_error_iter08"),
    str(REPORTS / "2026_10_08_position_error_iter01"),
    str(REPORTS / "2026_10_08_hard60_bounded_recovery"),
]
from baseline import load_case  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
from run import basis  # noqa: E402
from timing_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def load_basis(label, consumed):
    if label not in consumed or label == "DS17-008":
        case, document, base, _ = basis(label)
        return case, document, base
    case = load_case(label)
    document = json.loads(
        (REPORTS / "2026_10_08_position_error_iter01/baseline" / f"{label}.json").read_text()
    )
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
    return case, document, base


def run(label, protocol):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    binding = protocol["previous_results"][label]
    source = REPORTS / binding["path"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == binding["sha256"]
    previous = json.loads(source.read_text())
    chosen = next(
        r for r in previous["candidates"] if r["variant"] == "remove-5" and r["arm"] == "fitted-c"
    )
    assert chosen["converged"]
    case, document, base = load_basis(label, protocol["consumed_ds17_labels"])
    lookup = {int(n): i for i, n in enumerate(base.bank.numbers)}
    bank = base.bank.select([lookup[n] for n in chosen["satellites"]])
    subset = Hard60Objective(
        base.observations, bank, base.prior, base.score, receiver_baseline_hz=base.baseline
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], 2)
    np.testing.assert_allclose(
        model.evaluate_joint(seed, clock)[0], chosen["objective"], atol=1e-6, rtol=0
    )
    rows = []
    for variant, scale in protocol["variants"].items():
        model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], scale)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=clock))
            row.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, row["vector"], document)
            )
            rows.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 4), flush=True)
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            prior_result_sha256=binding["sha256"],
            satellites=bank.numbers.tolist(),
            removed=chosen["removed"],
            seed=seed,
            baseline_arms=previous["baseline_arms"],
            previous_candidates=[r for r in previous["candidates"] if r["variant"] == "remove-5"],
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == protocol["runner_sha256"]
    assert (
        hashlib.sha256((SOURCE / "timing_fit.py").read_bytes()).hexdigest()
        == protocol["fitter_sha256"]
    )
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, protocol)
