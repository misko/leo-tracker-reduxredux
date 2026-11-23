from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from named_roster_0155 import Ledger
from named_roster_0402 import BoundTrace, bound_route, trial_record


def test_bound_trace_records_original_native_and_fallback_without_affecting_other_owner():
    class Bound:
        def __init__(self):
            self.counts = {"calls": 0, "activated": 0, "fallback_unsupported": 0}

        def __call__(self, rows, design, *, fallback=False):
            self.counts["calls"] += 1
            self.counts["fallback_unsupported" if fallback else "activated"] += 1
            return {"noise_precision": [3., 4.], "precision_iterations": 2 * len(rows)}

    owner, other = Bound(), Bound()
    stamps = iter((10, 17, 20, 35))
    ledger = Ledger(lambda: 0)
    trace = BoundTrace(owner, ledger, timer=lambda: next(stamps))
    original = Bound.__call__
    design = SimpleNamespace(shape=(3, 4))
    with trace.instrument(), ledger.scope("history"):
        assert owner(range(3), design)["precision_iterations"] == 6
        with ledger.scope("proposal"):
            assert owner(range(3), design, fallback=True)["precision_iterations"] == 6
            assert other(range(3), design)["precision_iterations"] == 6
    assert Bound.__call__ is original
    assert trace.receipt() == [
        dict(scope="history", route="activated", observations=3, columns=4, groups=2,
             calls=1, cpu_ns=7, updates=6, max_updates=6, max_cpu_ns=7),
        dict(scope="proposal", route="fallback_unsupported", observations=3, columns=4, groups=2,
             calls=1, cpu_ns=15, updates=6, max_updates=6, max_cpu_ns=15),
    ]


def test_missing_likelihood_status_is_visible():
    before = {"calls": 0, "activated": 0, "fallback_unsupported": 0}
    with pytest.raises(ValueError, match="one original likelihood"):
        bound_route(before, dict(before, calls=1))


def test_rejected_cavity_trials_keep_both_arm_clocks_and_gates():
    arm = dict(corrected_selection_loss=8., final_phase_change_s=0.1, RMS_hz=155.,
               history=[{}, {}], gates={"tracks": [{"compatible": True}]})
    result = trial_record(dict(paired_valid=False, replacements=[{"candidate_index": 123}],
                              constrained_refinement_attempted=True,
                              arms={"c0": arm, "fitted_c": dict(arm, linear_gates=[{"compatible": False}])}))
    assert result["constrained"]
    assert not result["paired_valid"]
    assert result["arms"]["c0"]["failed_tracks"] == 0
    assert result["arms"]["fitted_c"]["failed_tracks"] == 1
