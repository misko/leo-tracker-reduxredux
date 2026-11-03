from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import ds23_joint_multilane_calibration as joint


def test_all_linear_additions_stay_predictive_without_new_calibration_columns(monkeypatch):
    p = SimpleNamespace()
    monkeypatch.setattr(joint, 'make_event_problem', lambda *args: p)
    monkeypatch.setattr(joint, 'polynomial_screen', lambda *args: None)
    captured = {}
    def attach(problem, entries, powers, anchors, covariances, correlated):
        captured.update(problem=problem, entries=entries, correlated=correlated)
        return problem
    monkeypatch.setattr(joint, 'attach_multilane_prediction', attach)
    original = dict(component='old'); new = dict(component='linear', track_index=0)
    d = dict(enriched=SimpleNamespace(tracks=[dict(times=np.arange(30.), values=np.arange(30.))]),
             mask=np.ones(30, bool), powers=np.ones(1), means=np.zeros(1), hyper={}, node={},
             covariance={'linear': {'marginal_sigma_hz': 100.}}, anchors={}, original_entries=[original])
    assert joint.joint_multilane_problem(d, 'c0', np.zeros(1), [new], True) is p
    assert p.joint_secondary_entries == [] and p.joint_conditional_powers == []
    assert captured['entries'] == [original, new] and captured['correlated']
