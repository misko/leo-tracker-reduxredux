"""Sealed 45-member development report; no inference reconstruction."""

import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = runpy.run_path(str(HERE / "report.py"))


def build():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = REPORT["sha"](HERE / "protocol.json")
    members = [
        m
        for m in plan["members"]
        if m.get("dataset", m["member"].get("dataset")) == "POST18-development"
    ]
    labels = [REPORT["member_label"](m) for m in members]
    expected = {f"POST18-NEWER-20261009-{i:03d}" for i in list(range(1, 9)) + list(range(17, 54))}
    assert len(members) == 45 and set(labels) == expected
    rows, hashes = [], {}
    for member in members:
        records, bound = REPORT["phase_receipts"](
            HERE / "results" / REPORT["member_label"](member), digest
        )
        assert REPORT["paired_terminal"](records)
        row = REPORT["describe_member"](member, records)
        row["exact_parity"] = {
            a: {
                k: records["baseline"].get("operational", {}).get(a, {}).get("fit", {}).get(k)
                == records["candidate"].get("operational", {}).get(a, {}).get("fit", {}).get(k)
                for k in ("vector", "clock_coefficients", "objective")
            }
            for a in REPORT["ARMS"]
        }
        for recovery in row["recoveries"]:
            for key in ("prefit_qualification", "postfit_qualification"):
                q = recovery.get(key)
                recovery[key] = (
                    None
                    if q is None
                    else {
                        k: q.get(k)
                        for k in (
                            "status",
                            "qualified",
                            "objective_evaluations",
                            "polish_elapsed_s",
                        )
                    }
                )
        rows.append(row)
        hashes.update(bound)
    assert len(hashes) == 90
    return dict(
        scope="Full frozen45 consumed newer development subset; reserves009..016 closed",
        protocol_sha256=digest,
        rows=rows,
        metrics=REPORT["aggregate"](rows),
        receipt_sha256=hashes,
    )


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, allow_nan=False))
