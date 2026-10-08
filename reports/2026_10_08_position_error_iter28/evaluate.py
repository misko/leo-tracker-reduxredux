"""Frozen stage canaries and reserved whole-scan validation; no retuning."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

# isort: off
from extension import REPORTS, extend_basis, extend_pipeline, load
from inputs import write_json
from newer import additional_region, load_member
from pipeline import run_pipeline
# isort: on

HERE = Path(__file__).resolve().parent


def protocol():
    value = json.loads((HERE / "protocol.json").read_text())
    for name, digest in value["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    return value


def canary(label, plan):
    path = HERE / "canaries" / f"{label}.json"
    if path.exists():
        raise FileExistsError("Preserve first canary")
    parent = json.loads((REPORTS / "2026_10_08_position_error_iter25/protocol.json").read_text())
    case, doc, base, correction, seed, clock, receipt = load(label, parent)
    result = extend_basis(case, doc, base, correction, seed, clock, receipt["previous_operational"])
    previous = json.loads(
        (REPORTS / "2026_10_08_position_error_iter27/results" / f"{label}.json").read_text()
    )
    for arm in ("fitted-c", "zero-c"):
        expected = next(
            r for r in previous["candidates"] if r["variant"] == "sigma-0.25" and r["arm"] == arm
        )
        actual = result["stages"]["slope-0.25"][arm]
        for key in ("vector", "clock_coefficients", "objective", "error_km"):
            np.testing.assert_allclose(actual[key], expected[key], atol=1e-6, rtol=0)
        assert actual["converged"] == expected["converged"]
    write_json(path, dict(status="complete", label=label, result=result, matched_atol=1e-6))
    print(label, "matched frozen iteration27", flush=True)


def reserved(label, plan):
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError("Preserve first reserved outcome")
    for name in plan["canaries"]:
        assert json.loads((HERE / "canaries" / f"{name}.json").read_text())["status"] == "complete"
    member = next(m for m in plan["members"] if m["label"] == label)
    if member["group"] == "validation":
        for development in (m for m in plan["members"] if m["group"] == "development"):
            row = json.loads((HERE / "results" / f"{development['label']}.json").read_text())
            assert row["status"] == "complete", "Resolve development execution first"
    try:
        case = load_member(member)
        write_json(HERE / "baselines" / f"{label}.json", case.document)
        additional, receipt = additional_region(case, label)
        write_json(HERE / "regions" / f"{label}.json", additional)
        upstream = run_pipeline(case, case.document, additional)
        result = extend_pipeline(case, case.document, additional, upstream)
        for rows in [*upstream["stages"].values(), *result["stages"].values()]:
            zero = rows["zero-c"]
            assert zero["vector"][6] == 0
            assert all(v == 0 for v in zero.get("rf_drift_coefficients", []))
        output = dict(
            status="complete",
            member=member,
            result=result,
            upstream=upstream,
            regional_receipt=receipt,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        )
    except Exception as error:
        write_json(path, dict(status="failed", member=member, error=repr(error)))
        raise
    write_json(path, output)
    print(label, {a: r["error_km"] for a, r in result["operational"].items()}, flush=True)


if __name__ == "__main__":
    plan = protocol()
    label = sys.argv[1]
    if label in plan["canaries"]:
        canary(label, plan)
    else:
        reserved(label, plan)
