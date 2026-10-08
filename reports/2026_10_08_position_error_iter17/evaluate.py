"""Matched density-weighting experiment across all 107 development scans."""

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
from inputs import json_value, write_json  # noqa: E402
from post_prune import load_basis  # noqa: E402
from probe import error_km  # noqa: E402
from timing_fit import fit  # noqa: E402
from weighted_clock import WeightedClockObjective, density_weights  # noqa: E402

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
    seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
    model = WeightedClockObjective(
        subset,
        correction["nodes_s"],
        correction["knots_hz"],
        np.ones(len(base.observations.times_s)),
    )
    if not fallback_seed:
        np.testing.assert_allclose(
            model.evaluate_joint(seed, clock)[0], chosen["objective"], atol=1e-6, rtol=0
        )
    terms = model.evaluate_joint(seed, clock)[3]
    groups = bank.numbers[terms.responsibilities.argmax(axis=1)].copy()
    groups[terms.responsibilities.max(axis=1) < 0.5] = 0
    rows = []
    for variant, power in protocol["variants"].items():
        weights = density_weights(base.observations, groups, power)
        model = WeightedClockObjective(
            subset, correction["nodes_s"], correction["knots_hz"], weights
        )
        for arm in ("fitted-c", "zero-c"):
            row = json_value(fit(model, seed, arm=arm, clock_seed=clock))
            row.update(
                variant=variant,
                arm=arm,
                error_km=error_km(case.prior, row["vector"], document),
                weight_min=float(weights.min()),
                weight_max=float(weights.max()),
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
            groups=groups,
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest
    shard = int(sys.argv[1])
    assert shard in (0, 1)
    for label in protocol["labels"][shard::2]:
        run(label, protocol)
