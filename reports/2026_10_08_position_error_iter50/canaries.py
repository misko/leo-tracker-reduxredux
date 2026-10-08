"""Verify unchanged stage assembly and the wider-region rescue with explicit provenance."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter45"))
# isort: off
from complete_members import load_case  # noqa: E402
from region_pipeline import run_pipeline  # noqa: E402
from extension import extend_pipeline  # noqa: E402
from inputs import write_json  # noqa: E402
# isort: on


def main(label):
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    binding = protocol["canaries"][label]
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    documents = {
        name: json.loads((REPORTS.parent / path).read_text())
        for name, path in binding["documents"].items()
    }
    expected = json.loads((REPORTS.parent / binding["expected"]).read_text())
    case = load_case(documents["baseline"], Path(binding["checkpoint_root"]))
    upstream = run_pipeline(case, documents)
    winning = documents[upstream["regional_sources"]["fitted-c"]]
    # Extension's two document slots receive the same explicit fitted-region source;
    # its numerical stages are unchanged and the actual three-way sources stay recorded.
    extension = extend_pipeline(case, winning, winning, upstream)
    errors = []
    for section, actual in (("upstream", upstream), ("extension", extension)):
        for stage, arms in actual["stages"].items():
            for arm, row in arms.items():
                old = expected[section]["stages"][stage][arm]
                for key in ("vector", "clock_coefficients", "objective", "error_km"):
                    np.testing.assert_allclose(row[key], old[key], atol=1e-5, rtol=0)
                assert row["converged"] == old["converged"]
                if arm == "zero-c":
                    assert row["vector"][6] == 0
                    assert all(v == 0 for v in row.get("rf_drift_coefficients", []))
                errors.append(abs(row["error_km"] - old["error_km"]))
    assert upstream["regional_sources"] == binding["expected_sources"]
    write_json(
        output,
        dict(
            status="complete",
            label=label,
            upstream=upstream,
            extension=extension,
            max_stage_error_difference_km=max(errors),
            tolerance=1e-5,
            protocol_sha256=hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        ),
    )
    print(label, upstream["regional_sources"], "matched all stage vectors and scores", flush=True)


if __name__ == "__main__":
    for label in sys.argv[1:]:
        main(label)
