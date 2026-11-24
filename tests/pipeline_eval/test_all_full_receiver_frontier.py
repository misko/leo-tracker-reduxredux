from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from all_full_receiver_frontier import assess, direct_donors, enrolled, requirement


def test_separate_paired_and_summed_break_even_rates():
    result = requirement([10., 10., 80.], [2., 2., 20.], [6., 6., 60.])
    assert result["required_rate"]["paired_median"] == pytest.approx(2.)
    assert result["required_rate"]["summed"] == pytest.approx(72/26)
    assert result["both"] == result["required_rate"]["summed"]


def test_zero_cost_floor_and_exact_half_time_limit():
    result = requirement([4., 4., 4.], [1., 1., 4.], [3., 3., 1.])
    assert result["required_rate"]["summed"] is None
    assert result["required_rate"]["paired_median"] == pytest.approx(3.)
    assert result["both"] is None
    tie = requirement([4., 4., 4.], [2., 2., 0.], [0., 0., 4.])
    assert tie["required_rate"]["paired_median"] == 1.


def test_installed_and_mixed_model_charge_only_disjoint_spans():
    case = dict(paid_installed_s=20., prefix=15., combined_solver_span=4.,
                mixed_outside_native=7.)
    model = assess([case], [12.])
    assert model["installed_if_only_native_changes"]["free_stage"]["total"] == 8.
    assert model["frontier"]["2"]["installed"]["free_stage"]["total"] == 10.
    assert model["frontier"]["2"]["installed"]["both"] is None
    assert model["charted_same_outside_native"]["both"] == pytest.approx(4.)


def test_signed_scope_and_entire_direct_full_callback_denominators():
    cases, donor = enrolled(), direct_donors()
    assert len(cases) == 30 and sum(2*c["admitted"] for c in cases) == 300522
    failure, = [c for c in cases if c["installed_outcome"] == "solver_failed"]
    assert failure["case"] == "DS30-0397" and failure["combined_solver_span"] > 0
    assert donor["DS30-0049"]["calls"] == 724
    assert donor["exact_chronological_DS30-0016"]["calls"] == 1426
