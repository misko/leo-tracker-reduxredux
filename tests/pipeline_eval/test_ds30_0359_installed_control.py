import pytest

from reports.ALGO08.v3.ds30_0359_installed_control import compare_cost


def test_paired_clocks_charge_own_checks_then_same_job_creation():
    both = ("elapsed_s", "cpu_s")
    candidate = dict(clock=dict.fromkeys(both, 15.), cost={key: {"setup": 1.} for key in both})
    costs = compare_cost(candidate, dict.fromkeys(both, 30.), dict.fromkeys(both, 2.), dict.fromkeys(both, .5))
    for arm in costs.values():
        assert arm["through_exit_ratio"] == 2.
        assert arm["admission_charged_ratio"] == 2.
        assert arm["candidate_admission_charged"] == 16.
        assert arm["installed_admission_charged"] == 32.
        assert arm["ratio_with_shared_original_setup"] == pytest.approx(32.5/16.5)
