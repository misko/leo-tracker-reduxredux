"""Complete the unavailable assigned member with the unchanged frozen candidate."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_08_position_error_iter20"
sys.path.insert(0, str(PREVIOUS))
# Frozen pipeline import installs the older report module paths.
# isort: off
from newer import additional_region, load_member  # noqa: E402
from pipeline import run_pipeline  # noqa: E402

from inputs import write_json  # noqa: E402
# isort: on


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest, name
    previous = json.loads((PREVIOUS / "validation-protocol.json").read_text())
    member = next(row for row in previous["members"] if row["label"] == protocol["label"])
    path = HERE / "result.json"
    if path.exists():
        raise FileExistsError("Preserve the completed numerical result")
    # A pending public status raises before any inference; no scan is replaced.
    case = load_member(member)
    write_json(HERE / "baseline.json", case.document)
    additional, receipt = additional_region(case, member["label"])
    write_json(HERE / "additional-region.json", additional)
    result = run_pipeline(case, case.document, additional)
    for rows in result["stages"].values():
        assert rows["zero-c"]["vector"][6] == 0
        assert all(value == 0 for value in rows["zero-c"].get("rf_drift_coefficients", []))
    write_json(
        path,
        dict(
            status="complete", member=member, result=result, regional_receipt=receipt,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
            scope="Completion only; preserve iteration 20's original failed availability gate",
        ),
    )
    print(json.dumps({a: row["error_km"] for a, row in result["operational"].items()}), flush=True)


if __name__ == "__main__":
    main()
