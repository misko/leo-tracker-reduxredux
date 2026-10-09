"""Completion-gated reporting for DS16 or full193; output goes to stdout only."""

import argparse
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = runpy.run_path(str(HERE / "report.py"))


def members_for(plan, scope):
    assert scope in ("DS16", "Full193")
    members = (
        plan["members"]
        if scope == "Full193"
        else [m for m in plan["members"] if m.get("dataset", m["member"].get("dataset")) == "DS16"]
    )
    assert len(members) == (193 if scope == "Full193" else 63)
    assert len({REPORT["member_label"](m) for m in members}) == len(members)
    return members


def require_terminal(members, phase_loader):
    """Finish this entire pass before any reference document loader can run."""
    for member in members:
        records, _ = phase_loader(member)
        if not REPORT["paired_terminal"](records):
            raise ValueError(f"Reporting deferred: {REPORT['member_label'](member)} not terminal")


def build(plan, scope, digest, *, phase_loader, document_loader=None):
    members = members_for(plan, scope)
    require_terminal(members, phase_loader)
    rows, hashes = [], {}
    for member in members:
        records, bound = phase_loader(member)
        row = REPORT["describe_member"](
            member, records, document_loader=document_loader or REPORT["evaluation_document"]
        )
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
    return dict(
        scope=scope + " completed consumed development snapshot",
        protocol_sha256=digest,
        rows=rows,
        metrics=REPORT["aggregate"](rows),
        datasets={
            d: REPORT["aggregate"]([r for r in rows if r["dataset"] == d])
            for d in sorted({r["dataset"] for r in rows})
        },
        receipt_sha256=hashes,
    )


def main(scope):
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = REPORT["sha"](HERE / "protocol.json")

    def loader(member):
        return REPORT["phase_receipts"](HERE / "results" / REPORT["member_label"](member), digest)

    result = build(plan, scope, digest, phase_loader=loader)
    for row in result["rows"]:
        row["runtime"] = REPORT["slice_metrics"](HERE / "results" / row["label"], digest)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("DS16", "Full193"), required=True)
    main(parser.parse_args().scope)
