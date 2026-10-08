"""Run the retained canary first, then the oracle-selected discarded region."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

# isort: off
from branch import REPORTS, downstream, regional
from inputs import write_json
from newer import load_member
# isort: on

HERE = Path(__file__).resolve().parent


def main(name):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for f, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    path = HERE / "results" / f"{name}.json"
    if path.exists():
        raise FileExistsError("Preserve first diagnostic result")
    if name != "retained":
        assert json.loads((HERE / "results/retained.json").read_text())["canary_passed"]
    previous = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())
    member = next(m for m in previous["members"] if m["label"] == "RESERVED-001")
    case = load_member(member)
    point = protocol["branches"][name]
    document, receipt = regional(case, point)
    canary = None
    if name == "retained":
        for arm in ("fitted-c", "zero-c"):
            actual = next(a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm)
            expected = next(
                a["selected"] for a in case.document["methods"][0]["arms"] if a["name"] == arm
            )
            for key in ("objective", "selection_score", "horizontal_error_m"):
                np.testing.assert_allclose(actual[key], expected[key], atol=1e-5, rtol=0)
            assert actual["satellites"] == expected["satellites"]
            expected_fit = next(
                r["fit"]
                for r in case.document["diagnostics"]["final_starts"]
                if r["arm"] == arm
                and r["basin"] == expected["source_basin"]
                and r["fit"]
                and abs(r["fit"]["objective"] - expected["objective"]) < 1e-9
            )
            np.testing.assert_allclose(actual["vector"], expected_fit["vector"], atol=1e-5, rtol=0)
        canary = True
    result = downstream(case, document)
    if name == "retained":
        expected = json.loads(
            (REPORTS / "2026_10_08_position_error_iter29/results/RESERVED-001.json").read_text()
        )
        for arm in ("fitted-c", "zero-c"):
            actual_row = result["extended"]["operational"][arm]
            expected_row = expected["result"]["operational"][arm]
            for key in ("vector", "clock_coefficients", "objective", "error_km"):
                np.testing.assert_allclose(actual_row[key], expected_row[key], atol=1e-5, rtol=0)
    write_json(
        path,
        dict(
            name=name,
            point=point,
            canary_passed=canary,
            scope=protocol["scope"],
            document=document,
            receipt=receipt,
            **result,
        ),
    )
    print(
        name, {a: r["error_km"] for a, r in result["extended"]["operational"].items()}, flush=True
    )


if __name__ == "__main__":
    main(sys.argv[1])
