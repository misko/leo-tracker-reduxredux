from types import SimpleNamespace
import numpy as np

import repair_ds23_iteration010_empty_prediction as repair


def test_empty_predictive_case_keeps_five_round_budget_without_predictive_api(monkeypatch):
    calls=[]
    p=SimpleNamespace(labels=[0],state=lambda x:dict(phases=np.zeros(1)))
    monkeypatch.setattr(repair.confirmation.experiment.binding.paths,'build',lambda *a:p)
    monkeypatch.setattr(repair,'fit',lambda *a,**kw:(calls.append(kw['iterations']) or dict(parameters=np.zeros(2))))
    monkeypatch.setattr(repair,'summary',lambda pp,x,entries:dict(endpoint_east_north_km=x,active_points=12,entries=entries))
    result=repair.refit_allow_empty(dict(entries=[],means=np.zeros(1)),'support','c0')
    assert calls==[48]*5
    assert result['audit']['no_predictive_observations'] and result['entries']==[]


def test_nonempty_case_uses_original_numerics_unchanged(monkeypatch):
    expected=object()
    monkeypatch.setattr(repair,'ORIGINAL_REFIT',lambda *a:expected)
    assert repair.refit_allow_empty(dict(entries=[1]),'default','fitted_c') is expected
