import pytest

from reports.ALGO08.v3.installed_receiver_first30 import FAILURE_SCOPE, NORMAL_SCOPE, clock_spans, scale_threshold


def scenario(failure=False):
    result = dict(outcome="solver_failed" if failure else "complete", elapsed_s=20. if failure else 21.,
                  cpu_s=15. if failure else 15.8, timing_scope=FAILURE_SCOPE if failure else NORMAL_SCOPE,
                  process=dict(started_unix_ns=1_000_000_000, finished_unix_ns=21_000_000_000,
                               elapsed_s=20., cpu_s=15., exit_code=int(failure), timed_out=False),
                  validation=dict(elapsed_s=1., cpu_s=.8), evidence=dict(terminal_file_s=18.))
    return result


def test_completed_timestamp_partition_and_cpu_capacity():
    measured = clock_spans(scenario(), 13_000_000_000, 13_200_000_000, 19_000_000_000)
    assert measured['through_native_write'] == 12
    assert measured['native_to_inventory_write'] == pytest.approx(.2)
    assert measured['inventory_to_terminal_write'] == pytest.approx(5.8)
    assert measured['terminal_to_exit'] == 2
    assert measured['verifier'] == 1
    assert measured['prefix_cpu_bound'] == dict(lower=6.99, upper=12.01)


def test_real_failure_exit_keeps_paid_suffix_and_excludes_separately_logged_diagnostic():
    row = scenario(failure=True)
    measured = clock_spans(row, 13_000_000_000, 13_200_000_000, None)
    assert measured['inventory_to_terminal_write'] == 0
    assert measured['inventory_to_failed_exit'] == pytest.approx(7.8)
    assert measured['verifier'] == measured['verifier_cpu'] == 0
    assert measured['actual_failure_diagnostic_not_in_scope'] == row['validation']
    with pytest.raises(ValueError, match='cannot partition'):
        clock_spans(row, 14_000_000_000, 13_200_000_000, None)


def test_budget_charges_both_gates_and_detects_impossible_free_floor():
    result = scale_threshold([10., 10., 100.], [4., 4., 0.], [6., 6., 100.])
    assert result['required_rate'] == pytest.approx(6)
    assert result['paired_median_required_rate'] > result['summed_required_rate']
    blocked = scale_threshold([10.,10.,100.], [6.,6.,0.], [4.,4.,100.])
    assert blocked['required_rate'] is None
    assert blocked['free']['paired_median'] == .6
    assert blocked['free']['summed'] == .1
