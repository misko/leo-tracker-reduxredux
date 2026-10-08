"""Check the assembled stage sequence on consumed scans before opening new data."""

import hashlib
import json
import sys
from pathlib import Path

from pipeline import run_pipeline

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter13"))
from inputs import write_json  # noqa: E402
from post_prune import load_basis  # noqa: E402

from leo.contracts.digests import canonical_digest  # noqa: E402


def run(label):
    protocol = json.loads((HERE / "integration-protocol.json").read_text())
    assert label in protocol["labels"]
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest
    previous = json.loads((REPORTS / "2026_10_08_position_error_iter13/protocol.json").read_text())
    case, _, _ = load_basis(label, previous["consumed_ds17_labels"])
    original = case.document
    if label.startswith("DS17"):
        original = json.loads(
            (REPORTS / "2026_10_08_position_error_iter01/baseline" / f"{label}.json").read_text()
        )
    selection = json.loads(
        (REPORTS / "2026_10_08_position_error_iter14/selection.json").read_text()
    )
    selected = next(r for r in selection["cases"] if r["label"] == label)
    assert canonical_digest(original) == selected["baseline_document_sha256"]
    path = REPORTS / selected["additional_document"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == selected["additional_file_sha256"]
    result = run_pipeline(case, original, json.loads(path.read_text()))
    reference_path = REPORTS / "2026_10_08_position_error_iter19/results" / f"{label}.json"
    expected = json.loads(reference_path.read_text())
    assert (
        hashlib.sha256(reference_path.read_bytes()).hexdigest()
        == protocol["expected_sha256"][label]
    )
    comparison = {}
    for arm in ("fitted-c", "zero-c"):
        row = result["operational"][arm]
        before = next(
            r for r in expected["candidates"] if r["arm"] == arm and r["variant"] == "drift-50"
        )
        assert before["converged"]
        comparison[arm] = dict(
            expected_error_km=before["error_km"],
            replay_error_km=row["error_km"],
            delta_km=row["error_km"] - before["error_km"],
            stage=row["stage"],
        )
    passed = all(
        abs(r["delta_km"]) < 0.001 and r["stage"] == "drift-50" for r in comparison.values()
    )
    write_json(
        HERE / "integration" / f"{label}.json",
        dict(label=label, passed=passed, comparison=comparison, result=result),
    )
    print(label, json.dumps(dict(passed=passed, comparison=comparison)), flush=True)
    assert passed, "Assembled stages differ from the qualified development result"


if __name__ == "__main__":
    run(sys.argv[1])
