"""Both timing priors receive all four saved arm/prior winners."""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

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
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError("Preserve first common-seed prior audit")
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
    previous = json.loads((REPORTS / "2026_10_08_position_error_iter38/selected.json").read_text())
    rows, audits = [], []
    for sigma in (2, 0.75):
        base = Hard60Objective(
            case.prepared.observations,
            bank,
            case.prior,
            replace(HARD60_SCORE, relative_sigma_s=sigma),
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        model = InitialClockObjective(
            base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
        )
        for source in [r for r in previous if r["label"] == label]:
            source_arm, source_sigma = source["arm"], source["sigma"]
            saved = source["after"]
            seed = np.asarray(saved["vector"])
            model.initial_clock = np.asarray(saved["clock_coefficients"])
            value, gradient, _, _ = model.evaluate_joint(seed, model.initial_clock)
            relative = model.basis @ seed[8:]
            expected = saved["objective"] + 0.5 * np.sum(relative**2) * (
                1 / sigma**2 - 1 / source_sigma**2
            )
            np.testing.assert_allclose(value, expected, atol=1e-6, rtol=0)
            audits.append(
                dict(
                    sigma=sigma,
                    source_arm=source_arm,
                    source_sigma=source_sigma,
                    objective=float(value),
                    c_hz_per_ghz=float(seed[6]),
                    c_gradient=float(gradient[6]),
                    local_center_km=seed[:2].tolist(),
                )
            )
            for arm in ("fitted-c", "zero-c"):
                row = json_value(initial_fit(model, seed.copy(), arm=arm))
                row.update(
                    sigma=sigma,
                    source_arm=source_arm,
                    source_sigma=source_sigma,
                    arm=arm,
                    error_km=error_km(case.prior, row["vector"], document),
                )
                if arm == "zero-c":
                    assert row["vector"][6] == 0
                rows.append(row)
                print(
                    label,
                    sigma,
                    source_arm,
                    source_sigma,
                    arm,
                    row["converged"],
                    row["objective"],
                    row["error_km"],
                    flush=True,
                )
    write_json(output, dict(label=label, seed_audits=audits, candidates=rows))


if __name__ == "__main__":
    main(sys.argv[1])
