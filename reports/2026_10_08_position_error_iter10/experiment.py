"""Truth-free timing-consistency policies with matched RF arms."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [
    str(HERE.parent / name)
    for name in (
        "2026_10_08_position_error_iter08",
        "2026_10_08_position_error_iter01",
        "2026_10_08_hard60_bounded_recovery",
    )
]
from inputs import json_value, write_json  # noqa: E402
from probe import error_km  # noqa: E402
from run import basis  # noqa: E402
from timing_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402


def reduce_bank(base, seed, limit):
    relative = base.basis @ seed[8:]
    keep = np.flatnonzero(abs(relative) <= limit)
    if len(keep) < 4:
        raise ValueError("insufficient candidates after timing gate")
    subset = Hard60Objective(
        base.observations,
        base.bank.select(keep),
        base.prior,
        base.score,
        receiver_baseline_hz=base.baseline,
    )
    shifts = (seed[7] + relative)[keep]
    projected = np.r_[seed[:7], shifts.mean(), subset.basis.T @ (shifts - shifts.mean())]
    np.testing.assert_allclose(projected[7] + subset.basis @ projected[8:], shifts, atol=1e-10)
    return subset, projected, base.bank.numbers[abs(relative) > limit].tolist()


def run(label, protocol):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    case, document, base, _ = basis(label)
    source = HERE.parent / "2026_10_08_position_error_iter08/results" / f"{label}.json"
    previous = json.loads(source.read_text())
    chosen = next(
        r
        for r in previous["previous_candidates"]
        if r["variant"] == "joint-wide" and r["arm"] == "fitted-c"
    )
    assert chosen["converged"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    results = []
    for variant in protocol["variants"]:
        subset, start, removed = base, seed, []
        if variant.startswith("remove-"):
            subset, start, removed = reduce_bank(base, seed, int(variant.split("-")[1]))
        model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], 2)
        bound = 5 if variant == "cap-5" else 20
        for arm in ("fitted-c", "zero-c"):
            result = json_value(
                fit(model, start, arm=arm, clock_seed=clock, timing_half_width_s=bound)
            )
            result.update(
                variant=variant,
                arm=arm,
                removed=removed,
                satellites=subset.bank.numbers.tolist(),
                error_km=error_km(case.prior, result["vector"], document),
            )
            results.append(result)
            print(
                label,
                variant,
                arm,
                result["converged"],
                round(result["error_km"], 4),
                removed,
                flush=True,
            )
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            prior_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            seed=seed,
            baseline_arms=previous["baseline_arms"],
            previous_candidates=previous["previous_candidates"],
            candidates=results,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, protocol)
