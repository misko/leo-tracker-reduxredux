from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from causal_cold_audit import duplicate_scope, without_timers


def point(model, position, fingerprint, cpu):
    return dict(model=model, exact_position=position, result_sha256=fingerprint, cpu_ns=cpu)


def test_repeated_position_in_different_phase_or_branch_cannot_be_reused():
    rows = [point(1, "0000", "a", 10), point(2, "0000", "b", 20), point(1, "8000", "c", 30),
            point(1, "0000", "a", 40), point(2, "0000", "b", 50)]
    assert duplicate_scope(rows) == dict(calls=5, exact_duplicates=2, cpu_ns=150, free_duplicate_ceiling_ns=90)


def test_same_coordinate_must_reproduce_the_entire_objective():
    with pytest.raises(ValueError, match="different objective bits"):
        duplicate_scope([point(1, "0000", "a", 10), point(1, "0000", "b", 20)])


def test_evidence_comparison_removes_only_diagnostic_clocks():
    assert without_timers(dict(branch=2, completed=[dict(cpu_ns=5, score=4, second_evaluations=17)])) == {
        "branch": 2, "completed": [{"score": 4, "second_evaluations": 17}],
    }
