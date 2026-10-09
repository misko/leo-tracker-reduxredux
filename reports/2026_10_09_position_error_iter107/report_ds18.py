"""Reporting-only sealed DS18 snapshot; no optimizer or inference reconstruction."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = runpy.run_path(str(HERE / "report.py"))


def build():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = REPORT["sha"](protocol)
    members = [m for m in plan["members"] if m.get("dataset", m["member"].get("dataset")) == "DS18"]
    assert len(members) == 34
    rows, hashes = [], {}
    for member in members:
        records, bound = REPORT["phase_receipts"](
            HERE / "results" / REPORT["member_label"](member), digest
        )
        assert all(r["status"] == "complete" for r in records.values())
        row = REPORT["describe_member"](member, records)
        assert row["evaluation_status"] == "post-fit-evaluation-only"
        row["exact_parity"] = {
            a: {
                k: records["baseline"]["operational"][a]["fit"].get(k)
                == records["candidate"]["operational"][a]["fit"].get(k)
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
    assert len(hashes) == 68
    return dict(
        scope="Completed DS18 subset34; other159 members not summarized",
        protocol_sha256=digest,
        rows=rows,
        metrics=REPORT["aggregate"](rows),
        receipt_sha256=hashes,
        report_source_sha256=hashlib.sha256((HERE / "report.py").read_bytes()).hexdigest(),
        exposure_note="24 previously consumed; ten without registry match are not proven unseen",
    )


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, allow_nan=False))
