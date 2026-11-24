from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from named_inference_budget import Ledger, disjoint, wall_and_decisions


def test_parent_cpu_is_reconciled_without_double_counting_nested_work():
    ticks = iter([0, 2, 5, 9, 13, 17])
    ledger = Ledger(timer=lambda: next(ticks))
    with ledger.scope("infer"):
        with ledger.scope("nomination"):
            with ledger.scope("likelihood"):
                pass
    assert disjoint(ledger.amounts, ("nomination", "cavity")) == {
        "nomination": 11, "cavity": 0, "between_ports": 6,
    }
    assert ledger.amounts["nomination"]["exclusive_cpu_ns"] == 7


def test_overlap_in_top_level_rows_is_rejected():
    calls = {"infer": {"inclusive_cpu_ns": 10}, "rank": {"inclusive_cpu_ns": 11}}
    with pytest.raises(ValueError, match="overlap"):
        disjoint(calls, ("rank",))


def test_real_offer_and_failure_status_are_preserved():
    stage_s = {"cavity": 0.2}
    measured = wall_and_decisions({"status": "withheld", "metrics": {"cavity_offered": False}}, stage_s)
    stage_s["evidence"] = 0.3
    assert measured["original_stage_wall_s"] == {"cavity": 0.2}
    assert measured["stages"]["status"] == "withheld"
    assert measured["stages"]["cavity_offered"] is False
