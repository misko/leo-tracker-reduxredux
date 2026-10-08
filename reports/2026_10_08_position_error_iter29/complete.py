"""Complete the unchanged reserved protocol while retaining iteration28's failed attempt."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter28"))
# isort: off
from extension import extend_pipeline  # noqa: E402
from inputs import write_json  # noqa: E402
from newer import additional_region, load_member  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
# isort: on


def main(label):
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    for name in plan["canaries"]:
        path = REPORTS / "2026_10_08_position_error_iter28/canaries" / f"{name}.json"
        assert json.loads(path.read_text())["status"] == "complete"
    member = next(m for m in plan["members"] if m["label"] == label)
    if member["group"] == "validation":
        for development in (m for m in plan["members"] if m["group"] == "development"):
            row = json.loads((HERE / "results" / f"{development['label']}.json").read_text())
            assert row["status"] == "complete", "Resolve development execution first"
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError("Preserve first completion attempt")
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
            scope="Unchanged model completion; iteration28 availability failure retained",
        )
    except Exception as error:
        write_json(path, dict(status="failed", member=member, error=repr(error)))
        raise
    write_json(path, output)
    print(label, {a: r["error_km"] for a, r in result["operational"].items()}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
