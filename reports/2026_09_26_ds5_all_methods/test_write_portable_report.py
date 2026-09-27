from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PATH = Path(__file__).with_name("write_portable_report.py")
SPEC = importlib.util.spec_from_file_location("ds5_write_portable_report", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_comparison_rows_preserve_all_eight_methods_and_scope_counts() -> None:
    scopes = []
    for method in MODULE.METHOD_LABELS:
        for scope, count, value in (("single", 42, 3.0), ("group8", 5, 2.0), ("full", 1, 1.0), ("rate_full", 4, 1.5)):
            scopes.append({"key": [scope, method], "expected_count": count, "complete_count": count, "median_error_km": value})
    document = {"summaries": {"scope_method": scopes}}
    rows = MODULE.comparison_rows(document)
    assert len(rows) == 8
    assert all(row["complete_count"] == 52 and row["expected_count"] == 52 for row in rows)
    assert all(row["full_error_km"] == 1.0 for row in rows)


def test_markdown_marks_missing_values_pending() -> None:
    row = {
        "method_label": "Baseline",
        "single_median_error_km": None,
        "group8_median_error_km": 2.0,
        "full_error_km": None,
        "rate_full_median_error_km": 1.5,
        "complete_count": 2,
        "expected_count": 4,
    }
    rendered = MODULE.markdown_table([row])
    assert "pending" in rendered
    assert "2/4" in rendered
