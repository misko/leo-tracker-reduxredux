import numpy as np
import pytest
from profile_algo07v3_training_queue import measured_mapper, schedule_bounds

from leo.operations.localization_v3_parallel import map_annotation_training


def test_known_schedule_bound_does_not_claim_measured_gain():
    result = schedule_bounds([1., 1., 10., 10., 1., 1.])
    assert result['fifo_seconds'] == 11
    assert result['optimistic_best_seconds'] == result['lower_bound_seconds'] == 10
    assert result['prescient'] and result['measured_speedup'] is None


@pytest.mark.parametrize('values', [[], [1] * 7, [-1], [float('nan')], [float('inf')]])
def test_invalid_duration_evidence(values):
    with pytest.raises(ValueError):
        schedule_bounds(values)


def test_serial_observer_preserves_result_identity_and_order():
    values = [object(), object()]
    rows = []
    actual = measured_mapper(map, rows, 'scoring')(lambda i: values[i], [1, 0])
    assert actual[0] is values[1] and actual[1] is values[0]
    assert [r['item'] for r in rows[0]['tasks']] == [1, 0]
    assert all(r['end'] >= r['start'] for r in rows[0]['tasks'])


def test_real_training_queue_preserves_records():
    def operation(item):
        return dict(task=item, keep=np.array([True, False, True]),
                    metadata=dict(history=[dict(phase_change_s=.25)]))
    tasks = [(seed, arm) for seed in (1, 2, 3) for arm in ('c0', 'fitted_c')]
    rows = []
    result = measured_mapper(map_annotation_training, rows, 'training')(operation, tasks)
    assert [r['task'] for r in result] == tasks
    assert all(r['training_points'] == 2 and r['phase_changes'] == [.25]
               for r in rows[0]['tasks'])
    assert len(rows[0]['tasks']) == 6


def test_failure_propagates_without_successful_block():
    def fail(item):
        raise RuntimeError('intentional')
    rows = []
    with pytest.raises(RuntimeError, match='intentional'):
        measured_mapper(map, rows, 'scoring')(fail, [0])
    assert rows == []
