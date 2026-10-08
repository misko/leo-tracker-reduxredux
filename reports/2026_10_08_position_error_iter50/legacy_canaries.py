"""Qualify the historical staged DS16/DS17 results against the assembled pipeline."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter28"))
# isort: off
from extension import extend_pipeline  # noqa: E402
from region_pipeline import run_pipeline  # noqa: E402
from baseline import load_case as load_ds17  # noqa: E402
from inputs import load_case as load_ds16, write_json  # noqa: E402
# isort: on


def main(label):
    protocol = json.loads((HERE / "legacy-protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS.parent / name).read_bytes()).hexdigest() == digest, name
    output = HERE / "results" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    case = load_ds17(label) if label.startswith("DS17-") else load_ds16(label)
    binding = protocol["canaries"][label]
    baseline = (
        json.loads((REPORTS.parent / binding["baseline"]).read_text())
        if binding["baseline"]
        else case.document
    )
    additional = (
        json.loads((REPORTS.parent / binding["additional"]).read_text())
        if binding["additional"]
        else baseline
    )
    documents = dict(baseline=baseline, sep25=additional, sep50=additional)
    upstream = run_pipeline(case, documents)
    winning = documents[upstream["regional_sources"]["fitted-c"]]
    extension = extend_pipeline(case, winning, winning, upstream)
    previous = json.loads(
        (REPORTS / "2026_10_08_position_error_iter27/results" / f"{label}.json").read_text()
    )
    for arm in ("fitted-c", "zero-c"):
        actual = extension["stages"]["slope-0.25"][arm]
        expected = next(
            r for r in previous["candidates"] if r["arm"] == arm and r["variant"] == "sigma-0.25"
        )
        for key in ("vector", "clock_coefficients", "objective", "error_km"):
            np.testing.assert_allclose(actual[key], expected[key], atol=1e-5, rtol=0)
        assert actual["converged"] == expected["converged"]
    write_json(
        output,
        dict(
            status="complete",
            label=label,
            upstream=upstream,
            extension=extension,
            tolerance=1e-5,
            scope="Matched historical staged final vectors/clocks/scores",
        ),
    )
    print(label, "matched historical staged result", upstream["regional_sources"], flush=True)


if __name__ == "__main__":
    for label in sys.argv[1:]:
        main(label)
