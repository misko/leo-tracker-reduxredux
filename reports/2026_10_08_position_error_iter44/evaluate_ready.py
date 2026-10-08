"""Continue the frozen candidate on newly reconciled, compatible members."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("20", "28")]
# isort: off
from newer import additional_region, load_member  # noqa: E402
from extension import extend_pipeline  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from inputs import write_json  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402
# isort: on


def run(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    row = next(r for r in protocol["ready"] if r["member"]["inventory_label"] == label)
    member = row["member"]
    path = HERE / "results" / f"{label}.json"
    if path.exists():
        raise FileExistsError(path)
    try:
        case = load_member(member)
        assert canonical_digest(case.document) == row["document_digest"]
        additional, receipt = additional_region(case, label)
        write_json(HERE / "regions" / f"{label}.json", additional)
        upstream = run_pipeline(case, case.document, additional)
        extension = extend_pipeline(case, case.document, additional, upstream)
        for stage in (*upstream["stages"].values(), *extension["stages"].values()):
            zero = stage["zero-c"]
            if "vector" in zero:
                assert zero["vector"][6] == 0
                assert all(v == 0 for v in zero.get("rf_drift_coefficients", []))
        output = dict(
            status="complete", member=member, upstream=upstream,
            extension=extension, regional_receipt=receipt,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        )
    except Exception as error:
        write_json(path, dict(status="failed", member=member, error=repr(error)))
        raise
    write_json(path, output)
    print(label, {a: r["error_km"] for a, r in extension["operational"].items()}, flush=True)


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
