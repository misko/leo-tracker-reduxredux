"""Matched downstream replay from original versus recovered joint solutions."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import extend_pipeline  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import load_member  # noqa: E402
from resume_pipeline import run_pipeline  # noqa: E402
# isort: on


def main(label):
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    case = load_member(next(m for m in members if m["label"] == label))
    binding = plan["cases"][label]
    source = json.loads((REPORTS / binding["document"]).read_text())
    document = source["document"] if binding["nested_document"] else source
    historical = json.loads((REPORTS / binding["control"]).read_text())
    selected = json.loads((REPORTS / "2026_10_08_position_error_iter39/selected.json").read_text())
    recovered = {
        arm: next(
            r["after"]
            for r in selected
            if r["label"] == label and r["sigma"] == 2 and r["arm"] == arm
        )
        for arm in ("fitted-c", "zero-c")
    }
    for mode, joint in (
        ("control", historical["upstream"]["stages"]["joint-100"]),
        ("recovered", recovered),
    ):
        output = HERE / "results" / f"{label}-{mode}.json"
        if output.exists():
            raise FileExistsError("Preserve first downstream replay")
        upstream = run_pipeline(case, document, document, joint)
        extended = extend_pipeline(case, document, document, upstream)
        if mode == "control":
            expected_extension = historical.get("extended", historical.get("result"))
            for actual, expected in (
                (upstream, historical["upstream"]),
                (extended, expected_extension),
            ):
                assert actual["stopped"] == expected["stopped"]
                assert actual.get("satellites") == expected.get("satellites")
                for stage, arms in actual["stages"].items():
                    for arm, row in arms.items():
                        saved = expected["stages"][stage][arm]
                        assert row["converged"] == saved["converged"]
                        for key in ("vector", "clock_coefficients", "objective", "error_km"):
                            np.testing.assert_allclose(row[key], saved[key], atol=1e-5, rtol=0)
        write_json(
            output,
            dict(
                label=label,
                mode=mode,
                upstream=upstream,
                extended=extended,
                canary_passed=mode == "control",
            ),
        )
        print(
            label,
            mode,
            "stopped",
            upstream["stopped"],
            "removed",
            upstream.get("removed"),
            "errors",
            {arm: row["error_km"] for arm, row in extended["operational"].items()},
            flush=True,
        )


if __name__ == "__main__":
    main(sys.argv[1])
