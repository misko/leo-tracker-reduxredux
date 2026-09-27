from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def runner():
    spec = importlib.util.spec_from_file_location("application_early_exit_validation", HERE / "run_validation.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selection_is_two_development_cases_without_holdout() -> None:
    module = runner()
    cases = module.selected_cases()
    assert tuple(case["case_id"] for case in cases) == module.CASE_IDS
    assert tuple(case["rate_hz"] for case in cases) == module.RATES
    assert all(case["split"] == "dev" and not case.get("is_holdout", False) for case in cases)


def test_schedule_has_three_calls_per_method() -> None:
    module = runner()
    flattened = [method for pair in module.SCHEDULE for method in pair]
    assert flattened == [
        "baseline", "candidate", "candidate", "baseline", "baseline", "candidate"
    ]
    assert flattened.count("baseline") == flattened.count("candidate") == 3


def test_design_freezes_two_rate_cpu_acceptance_gate() -> None:
    design = json.loads((HERE / "design.json").read_text())
    assert design["status"] == "frozen_before_timed_real_calls"
    assert any("3.0x" in gate and "both rates" in gate for gate in design["gates"])
    assert any("report-only" in gate for gate in design["gates"])
