import csv
from pathlib import Path

import pytest

from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.qualification import bounded_cavity_results as audit
from tools.pipeline_eval.qualification import bounded_cavity_trial as trial


def attempt(ident):
    root = trial.REPORT
    proof = audit.seal(root, "prediction-lock.json", ("plan.json", "capped.jsonl.gz"))
    assert ident in proof["cases"]
    rows = read_predictions(root / "capped.jsonl.gz")
    return rows[ident], audit.read(root / "plan.json")["source"], audit.sha(root / "plan.json")


def test_cavity_result_preserves_both_scientific_endpoints_on_completed_capped_input():
    row, plan, lock = attempt("DS26-0026")
    audit.validate_attempt(row, plan, lock)
    ref = read_predictions(trial.REPORT / "stock.jsonl.gz")[row["id"]]
    assert row["result"]["arms"] == ref["result"]["arms"]
    assert row["samples"][-1]["peak_bytes"] < trial.CAP
    assert all(sample["swap_bytes"] == 0 for sample in row["samples"])


@pytest.mark.parametrize("field", ["cpu", "swap_bytes", "peak_bytes", "stage"])
def test_runtime_proof_rejects_changes_in_accounting_or_missing_finish(field):
    row, plan, lock = attempt("DS26-0026")
    sample = row["samples"][-1]
    sample[field] = {
        "cpu": 999,
        "swap_bytes": 4096,
        "peak_bytes": trial.CAP + 1,
        "stage": "signed_context",
    }[field]
    with pytest.raises(ValueError):
        audit.validate_attempt(row, plan, lock)


def test_memory_kills_require_a_terminal_signal_and_stay_in_the_denominator(tmp_path):
    row, plan, lock = attempt("DS26-0146")
    previous, verdict = trial.result_for(
        "Finished with result: oom-kill", 1, Path(tmp_path) / "no-result"
    )
    assert verdict == "oom-kill" and previous == row["result"]
    audit.validate_attempt(row, plan, lock)
    row["terminal"] = "success"
    with pytest.raises(ValueError, match="termination"):
        audit.validate_attempt(row, plan, lock)
    with (trial.REPORT / "scores.csv").open() as stream:
        records = [r for r in csv.DictReader(stream) if r["method"] == "capped"]
    assert len(records) == 8
    assert sum(r["returned"] == "True" for r in records) == 2
