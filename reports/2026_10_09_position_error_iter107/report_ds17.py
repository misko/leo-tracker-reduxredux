"""Reporting-only completed DS17 snapshot, retaining all51 authority members."""

import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = runpy.run_path(str(HERE / "report.py"))


def build():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = REPORT["sha"](HERE / "protocol.json")
    members = [m for m in plan["members"] if m.get("dataset", m["member"].get("dataset")) == "DS17"]
    assert len(members) == 51
    assert {REPORT["member_label"](m) for m in members} == {f"DS17-{i:03d}" for i in range(1, 52)}
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
    assert len(hashes) == 102
    return dict(
        scope="Completed DS17 subset51, consumed development; no full193 claim",
        protocol_sha256=digest,
        rows=rows,
        metrics=REPORT["aggregate"](rows),
        receipt_sha256=hashes,
    )


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, allow_nan=False))
