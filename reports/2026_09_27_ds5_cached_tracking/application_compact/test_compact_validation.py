"""Compact full-application validation harness checks."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _runner():
    spec = importlib.util.spec_from_file_location("application_compact_validation", HERE / "run_validation.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selection_is_two_development_cases_without_holdout() -> None:
    module = _runner()
    cases = module.selected_cases()
    assert tuple(case["case_id"] for case in cases) == module.CASE_IDS
    assert tuple(case["rate_hz"] for case in cases) == module.RATES
    assert all(case["split"] == "dev" and not case.get("is_holdout", False) for case in cases)


def test_counterbalanced_schedule_has_three_calls_per_method() -> None:
    module = _runner()
    flattened = [method for pair in module.SCHEDULE for method in pair]
    assert flattened == [
        "baseline", "candidate", "candidate", "baseline", "baseline", "candidate"
    ]
    assert flattened.count("baseline") == flattened.count("candidate") == 3
