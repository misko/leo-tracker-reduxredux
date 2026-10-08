"""Matched time-varying RF stretch experiment on 107 development scans."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [
    str(REPORTS / "2026_10_08_position_error_iter13"),
    str(REPORTS / "2026_10_08_hard60_bounded_recovery"),
]
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from post_prune import load_basis  # noqa: E402
from probe import error_km  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402


def run(label, protocol):
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        return
    source = REPORTS / "2026_10_08_position_error_iter13/results" / f"{label}.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == protocol["inputs"][label]
    previous = json.loads(source.read_text())
    case, document, base = load_basis(label, protocol["consumed_ds17_labels"])
    lookup = {int(n): i for i, n in enumerate(base.bank.numbers)}
    bank = base.bank.select([lookup[n] for n in previous["satellites"]])
    subset = Hard60Objective(
        base.observations, bank, base.prior, base.score, receiver_baseline_hz=base.baseline
    )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    correction = document["diagnostics"]["calibrations"][selected["source_basin"]]["correction"]
    chosen = next(
        r for r in previous["candidates"] if r["variant"] == "post-200" and r["arm"] == "fitted-c"
    )
    fallback_seed = not chosen["converged"]
    if fallback_seed:
        chosen = next(r for r in previous["previous_candidates"] if r["arm"] == "fitted-c")
    assert chosen["converged"]
    seed, clock = np.asarray(chosen["vector"]), np.r_[chosen["clock_coefficients"], 0.0, 0.0]
    model = DynamicRFObjective(subset, correction["nodes_s"], correction["knots_hz"], 0)
    if not fallback_seed:
        np.testing.assert_allclose(
            model.evaluate_joint(seed, clock)[0], chosen["objective"], atol=1e-6, rtol=0
        )
    rows = []
    for variant, sigma in protocol["variants"].items():
        model = DynamicRFObjective(subset, correction["nodes_s"], correction["knots_hz"], sigma)
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=clock))
            row.update(
                variant=variant,
                arm=arm,
                error_km=error_km(case.prior, row["vector"], document),
            )
            rows.append(row)
            print(label, variant, arm, row["converged"], round(row["error_km"], 4), flush=True)
    write_json(
        output,
        dict(
            label=label,
            source_sha256=protocol["inputs"][label],
            session_id=document["session_id"],
            fallback_seed=fallback_seed,
            seed=seed,
            satellites=bank.numbers.tolist(),
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest
    shard = int(sys.argv[1])
    assert shard in range(4)
    for label in protocol["labels"][shard::4]:
        run(label, protocol)
