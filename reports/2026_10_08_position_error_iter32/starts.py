"""Carry a pre-existing zero-timing regional start through the unchanged joint chain."""

import copy
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import downstream, error_km  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import load_member  # noqa: E402
# isort: on


def main(label):
    plan = json.loads((HERE / "protocol.json").read_text())
    for f, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / f).read_bytes()).hexdigest() == digest, f
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError("Preserve first delayed-selection probe")
    parent = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())
    member = next(m for m in parent["members"] if m["label"] == label)
    case = load_member(member)
    binding = plan["cases"][label]
    source = json.loads((REPORTS / binding["document"]).read_text())
    original = source["document"] if binding["nested_document"] else source
    diagnostics = copy.deepcopy(original["diagnostics"])
    arms = []
    for arm in ("fitted-c", "zero-c"):
        selected = next(a["selected"] for a in original["methods"][0]["arms"] if a["name"] == arm)
        rows = [
            r
            for r in diagnostics["final_starts"]
            if r["arm"] == arm and r["basin"] == binding["basin"] and r["start"] == "zero-timing"
        ]
        assert len(rows) == 1 and selected["source_basin"] == binding["basin"]
        row = rows[0]
        fit = row["fit"]
        assert fit and fit["converged"], "Do not substitute an unavailable or nonstationary seed"
        chosen = dict(
            **fit,
            source_basin=binding["basin"],
            satellites=selected["satellites"],
            selection_score=fit["objective"] + row["calibration_penalty"],
            calibration_penalty=row["calibration_penalty"],
            horizontal_error_m=1000 * error_km(case.prior, fit["vector"], original),
        )
        arms.append(dict(name=arm, selected=chosen))
    document = dict(
        scope="Private forced-start diagnostic input, not a public position document",
        methods=[dict(arms=arms)],
        diagnostics=diagnostics,
        reference_latitude_deg=original["reference_latitude_deg"],
        reference_longitude_deg=original["reference_longitude_deg"],
    )
    result = downstream(case, document)
    write_json(path, dict(label=label, scope=binding["scope"], document=document, **result))
    print(
        label, {a: r["error_km"] for a, r in result["extended"]["operational"].items()}, flush=True
    )


if __name__ == "__main__":
    main(sys.argv[1])
