"""Oracle-only nuisance profiles of remaining post-200 position failures."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [
    str(REPORTS / "2026_10_08_position_error_iter13"),
    str(REPORTS / "2026_10_08_position_error_iter09"),
]
from profile import decompose, reference_point  # noqa: E402

from inputs import json_value, write_json  # noqa: E402
from post_prune import load_basis  # noqa: E402
from probe import error_km  # noqa: E402
from profile_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402


def run(label, protocol):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    source = REPORTS / "2026_10_08_position_error_iter13/results" / f"{label}.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == protocol["inputs"][label]
    previous = json.loads(source.read_text())
    source_protocol = json.loads(
        (REPORTS / "2026_10_08_position_error_iter13/protocol.json").read_text()
    )
    case, document, base = load_basis(label, source_protocol["consumed_ds17_labels"])
    lookup = {int(n): i for i, n in enumerate(base.bank.numbers)}
    bank = base.bank.select([lookup[n] for n in previous["satellites"]])
    subset = Hard60Objective(
        base.observations, bank, base.prior, base.score, receiver_baseline_hz=base.baseline
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    model = JointClockObjective(subset, correction["nodes_s"], correction["knots_hz"], 4)
    chosen = next(
        r for r in previous["candidates"] if r["variant"] == "post-200" and r["arm"] == "fitted-c"
    )
    assert chosen["converged"]
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    terms = model.evaluate_joint(seed, clock)
    np.testing.assert_allclose(terms[0], chosen["objective"], atol=1e-6, rtol=0)
    groups = model.bank.numbers[terms[3].responsibilities.argmax(axis=1)].copy()
    groups[terms[3].responsibilities.max(axis=1) < 0.5] = 0
    truth = reference_point(
        case.prior,
        document["reference_latitude_deg"],
        document["reference_longitude_deg"],
        seed[:2],
    )
    steps = int(np.ceil(np.linalg.norm(truth - seed[:2]) / 0.25))
    assert 1 <= steps <= 20
    rows = []
    for arm in ("fitted-c", "zero-c"):
        current = None
        completed = True
        for step in range(steps + 1):
            point = seed[:2] + (truth - seed[:2]) * step / steps
            start = seed.copy() if current is None else np.asarray(current["vector"]).copy()
            start[:2] = point
            clock_start = clock if current is None else current["clock_coefficients"]
            attempts = []
            for retry in range(3):
                result = json_value(
                    fit(model, start, arm=arm, fixed_position=True, clock_seed=clock_start)
                )
                result.update(
                    step=step,
                    retry=retry,
                    arm=arm,
                    error_km=error_km(case.prior, result["vector"], document),
                )
                result["decomposition"] = decompose(model, result, groups)
                attempts.append(result)
                if result["converged"]:
                    break
                start, clock_start = result["vector"], result["clock_coefficients"]
            rows.append(dict(arm=arm, step=step, attempts=attempts))
            print(
                label,
                arm,
                step,
                steps,
                result["converged"],
                round(result["objective"], 4),
                flush=True,
            )
            if not result["converged"]:
                completed = False
                break
            current = result
        if completed:
            released = json_value(
                fit(model, current["vector"], arm=arm, clock_seed=current["clock_coefficients"])
            )
            released.update(
                arm=arm,
                phase="reference-released",
                error_km=error_km(case.prior, released["vector"], document),
            )
            released["decomposition"] = decompose(model, released, groups)
            rows.append(released)
    write_json(
        output,
        dict(
            label=label,
            source_sha256=protocol["inputs"][label],
            fitted_selected=chosen,
            reference_point_km=truth,
            step_count=steps,
            satellites=bank.numbers.tolist(),
            group_counts={str(g): int((groups == g).sum()) for g in np.unique(groups)},
            rows=rows,
            reference_use="Oracle diagnostic only; never an operational initializer or result",
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for relative, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / relative).read_bytes()).hexdigest() == digest
    label = sys.argv[1]
    assert label in protocol["labels"]
    run(label, protocol)
