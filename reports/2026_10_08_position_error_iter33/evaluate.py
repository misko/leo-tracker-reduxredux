"""Matched relative-timing prior refits from two existing regional initializations."""

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
    for f, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError("Preserve first refit sweep")
    binding = plan["cases"][label]
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == label))
    original_source = json.loads((REPORTS / binding["document"]).read_text())
    original = original_source["document"] if binding["nested_document"] else original_source
    zero_source = json.loads(
        (REPORTS / "2026_10_08_position_error_iter32/results" / f"{label}.json").read_text()
    )
    zero = zero_source["document"]
    controls = {
        "original-start": json.loads((REPORTS / binding["control"]).read_text()),
        "zero-timing-start": zero_source,
    }
    selected = next(
        a["selected"] for a in original["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    numbers = selected["satellites"]
    cal = original["diagnostics"]["calibrations"][binding["basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in numbers])
    seeds = {}
    for name, doc in (("original-start", original), ("zero-timing-start", zero)):
        selected = next(a["selected"] for a in doc["methods"][0]["arms"] if a["name"] == "fitted-c")
        assert selected["satellites"] == numbers
        assert doc["diagnostics"]["calibrations"][binding["basin"]] == cal
        fitted = next(
            r["fit"]
            for r in doc["diagnostics"]["final_starts"]
            if r["arm"] == "fitted-c"
            and r["basin"] == binding["basin"]
            and r["fit"]
            and abs(r["fit"]["objective"] - selected["objective"]) < 1e-9
        )
        seeds[name] = np.asarray(fitted["vector"])
    rows = []
    for sigma in plan["relative_sigmas_s"]:
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
        for name, seed in seeds.items():
            for arm in ("fitted-c", "zero-c"):
                row = json_value(initial_fit(model, seed, arm=arm))
                row.update(
                    relative_sigma_s=sigma,
                    initialization=name,
                    arm=arm,
                    error_km=error_km(case.prior, row["vector"], original),
                )
                relative = model.basis @ np.asarray(row["vector"])[8:]
                row["relative_timing_rms_s"] = float(np.sqrt(np.mean(relative**2)))
                row["relative_seconds"] = relative.tolist()
                if arm == "zero-c":
                    assert row["vector"][6] == 0
                if sigma == 2:
                    expected = controls[name]["upstream"]["stages"]["joint-100"][arm]
                    for key in ("vector", "clock_coefficients", "objective", "error_km"):
                        np.testing.assert_allclose(row[key], expected[key], atol=1e-5, rtol=0)
                    assert row["converged"] == expected["converged"]
                rows.append(row)
                print(
                    label, sigma, name, arm, row["converged"], round(row["error_km"], 6), flush=True
                )
    write_json(
        output, dict(label=label, scope=binding["scope"], candidates=rows, satellites=numbers)
    )


if __name__ == "__main__":
    main(sys.argv[1])
