import numpy as np
import pytest
from profile_algo07v3_training_convergence import observe

from leo.analysis.localization_v3 import event_position, history_position, prediction


def test_preserves_outputs_and_phase_attribution(monkeypatch):
    value = dict(precision_iterations=256, final_log_precision_change=.01)
    operation = lambda *a, **kw: value  # noqa: E731
    fake_fit = lambda: event_position.hierarchical_bound(np.ones(3), np.ones((3, 2)))  # noqa: E731
    monkeypatch.setattr(event_position, 'hierarchical_bound', operation)
    monkeypatch.setattr(history_position, 'hierarchical_bound', operation)
    monkeypatch.setattr(prediction, 'fit', fake_fit)
    rows = []
    with observe(rows) as phase:
        assert prediction.fit() is value
        assert prediction.fit() is value
        phase[0] = 'signature'
        assert history_position.hierarchical_bound(np.ones(3), np.ones((3, 2))) is value
    assert [r['phase'] for r in rows] == [0, 1, 'signature']
    assert all(r['points'] == 3 and r['width'] == 2 and r['iterations'] == 256 for r in rows)
    assert event_position.hierarchical_bound is history_position.hierarchical_bound is operation
    assert prediction.fit is fake_fit


def test_failure_restores_all_aliases():
    originals = (event_position.hierarchical_bound,
                 history_position.hierarchical_bound, prediction.fit)
    rows = []
    with pytest.raises(RuntimeError), observe(rows):
        raise RuntimeError('intentional')
    assert originals == (event_position.hierarchical_bound,
                         history_position.hierarchical_bound, prediction.fit)
    assert rows == []
