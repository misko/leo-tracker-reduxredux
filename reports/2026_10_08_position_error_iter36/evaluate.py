"""Receiver-pair clock proposals as starts for the unchanged joint likelihood."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from consensus import propose

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import Hard60Objective, HARD60_SCORE, error_km  # noqa: E402
from pipeline import InitialClockObjective, initial_fit  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from newer import load_member  # noqa: E402
# isort: on


def main(label):
    plan = json.loads((HERE / "protocol.json").read_text())
    for f, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError("Preserve first clock-initialization test")
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == label))
    binding = plan["cases"][label]
    source = json.loads((REPORTS / binding["document"]).read_text())
    document = source["document"] if binding["nested_document"] else source
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    cal = document["diagnostics"]["calibrations"][binding["basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in selected["satellites"]])
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
    )
    model = InitialClockObjective(
        base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
    )
    previous = json.loads(
        (REPORTS / "2026_10_08_position_error_iter33/results" / f"{label}.json").read_text()
    )["candidates"]
    saved = next(
        r
        for r in previous
        if r["relative_sigma_s"] == 2
        and r["initialization"] == "original-start"
        and r["arm"] == "fitted-c"
    )
    seed = np.asarray(saved["vector"])
    model.initial_clock = np.asarray(saved["clock_coefficients"])
    np.testing.assert_allclose(
        model.evaluate_joint(seed, model.initial_clock)[0], saved["objective"], atol=1e-6, rtol=0
    )
    audit = json.loads(
        (REPORTS / "2026_10_08_position_error_iter34/results" / f"{label}.json").read_text()
    )
    paired = next(
        r
        for r in audit["candidates"]
        if r["relative_sigma_s"] == 2
        and r["initialization"] == "original-start"
        and r["arm"] == "fitted-c"
    )
    times = np.array([p["time_s"] for p in audit["pairs"]])
    times -= base.observations.time_center_s
    proposals = propose(times, np.asarray(paired["residual_hz"]))
    seeds = [("continued-original", seed.copy())]
    rejected = []
    for i, proposal in enumerate(proposals):
        for anchor in (0, 1):
            candidate = seed.copy()
            receiver, sign = (1, 1) if anchor == 0 else (0, -1)
            candidate[2 + receiver * 2] += sign * proposal["intercept_hz"]
            candidate[3 + receiver * 2] += sign * proposal["slope_hz_s"]
            name = f"proposal-{i + 1}-anchor-{anchor}"
            if abs(candidate[3 + receiver * 2]) > 60:
                rejected.append(
                    dict(
                        name=name,
                        reason="affine slope outside hard60",
                        slope_hz_s=float(candidate[3 + receiver * 2]),
                    )
                )
                continue
            seeds.append((name, candidate))
    rows = []
    for name, candidate in seeds:
        for arm in ("fitted-c", "zero-c"):
            row = json_value(initial_fit(model, candidate.copy(), arm=arm))
            row.update(
                initialization=name, arm=arm, error_km=error_km(case.prior, row["vector"], document)
            )
            if arm == "zero-c":
                assert row["vector"][6] == 0
            rows.append(row)
            print(label, name, arm, row["converged"], row["error_km"], flush=True)
    write_json(
        output,
        dict(
            label=label,
            proposals=proposals,
            rejected=rejected,
            candidates=rows,
            shared_seed=seed.tolist(),
            original_clock=model.initial_clock.tolist(),
        ),
    )


if __name__ == "__main__":
    main(sys.argv[1])
