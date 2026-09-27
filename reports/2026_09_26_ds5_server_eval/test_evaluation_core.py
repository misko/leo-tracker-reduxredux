import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'ds5_evaluation_core', Path(__file__).with_name('evaluation_core.py'))
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def candidate(**kwargs):
    return core.Candidate(**(dict(fractional_complete=True, margin=.1, cfo_hz=1000,
                                  epoch_seconds=1e-6, window_index=0) | kwargs))


def test_other_signal_is_not_retained_even_when_positive():
    result = core.compare_cases({'a': [candidate()]}, {'a': [candidate(cfo_hz=20000)]})
    assert result['reference_relative_retention'] == 0


def test_circular_timing_and_common_window():
    assert core.matches(candidate(), candidate(epoch_seconds=1/750 - .5e-6))
    assert not core.matches(candidate(), candidate(window_index=1))


def test_unprocessed_is_not_negative_and_missing_inventory_is_error():
    result = core.compare_cases({'a': [candidate()]}, {'a': None})
    assert result['unknown_cases'] == 1 and result['lost_reference_positive_cases'] == 1
    with pytest.raises(ValueError):
        core.compare_cases({'a': [candidate()]}, {})


def test_gate_requires_fractional_completion_and_strict_margin():
    assert not candidate(fractional_complete=False).positive
    assert not candidate(margin=.025).positive


def test_no_positives_does_not_imply_perfect_retention():
    result = core.compare_cases({'a': []}, {'a': [candidate()]})
    assert result['reference_relative_retention'] is None
    assert result['additional_positive_cases'] == 1


def test_unknown_reference_cannot_create_claimed_additional_positive():
    result = core.compare_cases({'a': None}, {'a': [candidate()]})
    assert result['reference_unknown_cases'] == 1
    assert result['additional_positive_cases'] == 0


def test_both_receivers_and_acquisition_time_count():
    job = core.VisitJob('s', 0, 0, .12, (40, 50))
    result = core.replay_serial_worker([job])
    assert result['median_service_ms'] == 90
    assert result['maximum_completion_age_ms'] == pytest.approx(210)


def test_queue_backlog_and_independent_session_reset():
    jobs = [core.VisitJob('s', 0, 0, .12, (100, 100)),
            core.VisitJob('s', 1, .135, .255, (100, 100)),
            core.VisitJob('t', 0, 0, .12, (100, 100))]
    result = core.replay_serial_worker(jobs)
    assert result['rows'][1]['queue_ms'] == pytest.approx(65)
    assert result['rows'][2]['queue_ms'] == 0


def test_skips_remain_unknown():
    result = core.replay_serial_worker([core.VisitJob('s', 0, 0, .12, (), False)])
    assert result['unknown_visits'] == 1
    assert result['median_service_ms'] is None


def test_rejects_future_reordering_and_invalid_measurements():
    with pytest.raises(ValueError):
        core.replay_serial_worker([core.VisitJob('s', 1, .135, .255, (1,)),
                                   core.VisitJob('s', 0, 0, .12, (1,))])
    with pytest.raises(ValueError):
        candidate(cfo_hz=float('nan'))
    with pytest.raises(ValueError):
        core.VisitJob('s', 0, 0, .12, (-1,))
