from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.portable_footprint import compare
from tools.pipeline_eval.qualification.portable_footprint_results import category, python_counts


def test_trace_union_counts_each_line_once_and_omits_implicit_functions():
    path = "/installed/leo/scanner/fast_scan_analysis.py"
    trace = [
        dict(path=path, name="production_glrt", definition=20, lines=[27, 28]),
        dict(path=path, name="production_glrt.<genexpr>", definition=28, lines=[28, 29]),
        dict(path=path, name="analyze_window", definition=50, lines=[51]),
    ]
    assert python_counts(trace) == dict(files=1, lines=4, code_objects=3, functions=2)
    assert [category(row) for row in trace] == ["abi", "abi", "public"]


def test_comparison_requires_exact_published_decision_and_bounded_numerics():
    candidate = {
        "candidate_rank": 1,
        "fractional_margin": 0.031,
        "passed_fractional_margin_gate": True,
    }
    reference = {"0": {"probes": [{"receiver_id": 0, "candidates": [candidate]}]}}
    result = deepcopy(reference)
    altered = result["0"]["probes"][0]["candidates"][0]
    altered["fractional_margin"] += 1e-13
    assert compare(reference, result)["counts"] == dict(
        visits=1, probes=1, candidates=1, positive=1
    )
    altered["candidate_rank"] = 0
    with pytest.raises(ValueError, match="candidate_rank"):
        compare(reference, result)
    altered["candidate_rank"] = 1
    altered["fractional_margin"] += 1e-10
    with pytest.raises(ValueError, match="fractional_margin"):
        compare(reference, result)
