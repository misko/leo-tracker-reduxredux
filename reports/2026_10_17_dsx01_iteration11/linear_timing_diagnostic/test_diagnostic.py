"""Owned synthetic invariance/accounting tests; no public orbit calls."""

from types import SimpleNamespace

import numpy as np
import pytest
from numpy.testing import assert_allclose, assert_array_equal

from diagnostic import CallLedger, DELTAS_S, select_training_rows, summarize


class Metadata(SimpleNamespace):
    @property
    def measured_hz(self):
        raise AssertionError('Measured response must never be accessed')

    @property
    def station(self):
        raise AssertionError('Reference coordinates must never be accessed')


def metadata(lanes=5, rows_per_lane=5):
    count = lanes * rows_per_lane
    return Metadata(window_ids=tuple(f'global-probe-{i}' for i in range(count)),
                    times_s=np.arange(count, dtype=float), rf_hz=np.full(count, 11e9),
                    receiver=np.repeat(np.arange(lanes) % 2, rows_per_lane),
                    channel=np.repeat(np.arange(lanes), rows_per_lane))


def test_train_only_metadata_selection_is_permutation_and_response_blind():
    m = metadata()
    train = np.arange(len(m.times_s)) % 3 != 0
    selected = select_training_rows(m, train)
    assert train[selected].all()
    order = np.random.default_rng(20261017).permutation(len(train))
    changed = Metadata(window_ids=tuple(m.window_ids[i] for i in order),
                       **{name: getattr(m, name)[order] for name in
                          ('times_s', 'rf_hz', 'receiver', 'channel')})
    changed_rows = select_training_rows(changed, train[order])
    assert tuple(m.window_ids[i] for i in selected) == tuple(changed.window_ids[i] for i in changed_rows)
    for lane in set(zip(m.receiver, m.channel, m.rf_hz)):
        assert sum((m.receiver[i], m.channel[i], m.rf_hz[i]) == lane for i in selected) <= 2


def test_global_cap_original_ids_and_actual_rf_define_separate_lanes():
    m = metadata(lanes=40)
    selected = select_training_rows(m, np.ones(len(m.times_s), bool))
    assert len(selected) == 32
    assert len(set(m.window_ids[i] for i in selected)) == 32
    m = metadata(lanes=1, rows_per_lane=4)
    m.rf_hz[2:] += 1e6
    assert len(select_training_rows(m, np.ones(4, bool))) == 4
    m.window_ids = ('duplicate',) * 4
    with pytest.raises(ValueError, match='Unique global'):
        select_training_rows(m, np.ones(4, bool))


def test_all_declared_port_calls_include_zero_and_reject_retry():
    snapshots = []
    ledger = CallLedger(lambda records: snapshots.append([dict(r) for r in records]))
    for arm in ('fitted-c', 'zero-c'):
        for delta in DELTAS_S:
            for kind in ('orbit', 'elevation'):
                assert ledger.call(kind, arm, delta, lambda: 17) == 17
    assert len(ledger.calls) == 36
    assert sum(r['delta_s'] == 0 for r in ledger.calls) == 4
    assert all(r['status'] == 'complete' for r in ledger.calls)
    assert snapshots[0][0]['status'] == 'started'
    with pytest.raises(ValueError, match='duplicate or retry'):
        ledger.call('orbit', 'fitted-c', 0., lambda: None)
    with pytest.raises(ValueError, match='declared'):
        ledger.call('orbit', 'fitted-c', 3., lambda: None)


def test_failed_call_is_persisted_and_cannot_be_retried():
    snapshots = []
    ledger = CallLedger(lambda records: snapshots.append([dict(r) for r in records]))
    def fail():
        assert snapshots[-1][0]['status'] == 'started'
        raise RuntimeError('synthetic port failure')
    with pytest.raises(RuntimeError, match='synthetic port failure'):
        ledger.call('orbit', 'zero-c', -6., fail)
    assert ledger.calls[0]['status'] == 'failed'
    with pytest.raises(ValueError, match='duplicate or retry'):
        ledger.call('orbit', 'zero-c', -6., lambda: None)


def test_summary_retains_all_errors_and_visibility_changes():
    error = np.array([[0., 1.], [-2., 3.]])
    sine = np.array([[-1., 1.], [0., -1.]])
    zero_sine = np.array([[1., 1.], [-1., -1.]])
    weight = np.array([[0., 1.], [.5, 0.]])
    zero_weight = np.array([[1., 1.], [0., 0.]])
    result = summarize(error, np.zeros_like(error), sine, zero_sine, weight, zero_weight)
    assert result['pairs'] == 4
    assert_allclose(result['rms_error_hz'], np.sqrt(3.5))
    assert result['maximum_absolute_error_hz'] == 3
    assert result['horizon_crossings'] == 2
    assert result['soft_weight_changes'] == 2
    assert result['maximum_soft_weight_change'] == 1
    assert_array_equal([result['signed_error_hz'][0], result['signed_error_hz'][-1]], [-2, 3])
    closure = summarize(error, error, sine, sine, weight, weight)
    assert closure['rms_error_hz'] == closure['horizon_crossings'] == closure['soft_weight_changes'] == 0
