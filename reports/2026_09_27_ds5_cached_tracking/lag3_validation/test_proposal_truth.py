import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'lag3_truth_score', Path(__file__).with_name('score.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_physical_frame_phase_and_exact_joint_gates():
    rate = 2_500_000
    truth = {'epoch_samples': rate / 750 - 1, 'cfo_hz': -399000}
    candidate = {'epoch_samples': 0, 'cfo_hz': -391000, 'window': 5}
    error = module.coordinate_error(candidate, truth, rate)
    assert error['timing_error_us'] == pytest.approx(0.4)
    assert error['coordinate_match']
    candidate['cfo_hz'] += 1
    assert not module.coordinate_error(candidate, truth, rate)['coordinate_match']


def test_unsupported_coordinate_match_is_not_accepted():
    case = {'rate_hz': 5_000_000, 'epoch_relative_samples': 571.49,
            'components': [{'type': 'pilot', 'cfo_hz': 399000}]}
    score = module.score_case(case, [dict(window=0, epoch_samples=571.49,
                                         cfo_hz=399000, supported=False)])
    assert score['any_coordinate_match']
    assert not score['any_supported_coordinate_match']
    assert score['detector_decision'] is None


def test_mixture_reports_each_truth_and_negatives_are_not_false_alarms():
    case = {'rate_hz': 2_500_000, 'epoch_relative_samples': 100,
            'components': [{'type': 'pilot', 'trajectory_id': 'a', 'cfo_hz': -100000},
                           {'type': 'pilot', 'trajectory_id': 'b', 'cfo_hz': 100000}]}
    candidate = dict(window=3, epoch_samples=100, cfo_hz=-100000, supported=True)
    score = module.score_case(case, [candidate])
    assert score['each_injected_pilot_supported'] == {'a': True, 'b': False}
    case['components'] = [{'type': 'tone'}]
    score = module.score_case(case, [candidate])
    assert score['any_supported_coordinate_match'] is None
    assert score['supported_proposal_count'] == 1
    assert score['false_alarm_rate_estimate'] is None
