import copy
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('ds24_adapter', Path(__file__).with_name('evaluate_ds24.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def example():
    arms = ('c0','fitted_c')
    d = dict(problems={a:(None,np.array([1.,2.])) for a in arms})
    z = dict(baseline_owners={a:{'point':123} for a in arms})
    baseline = {a:dict(associated=1) for a in arms}
    receipt = dict(schema='ds24-saved-algo06-authority/v1', source='saved research', source_sha256={},
        arms={a:dict(x=[1.,2.],objective=5.) for a in arms}, owners=copy.deepcopy(z['baseline_owners']))
    return d,z,baseline,receipt


def test_saved_baseline_requires_exact_ownership_and_coordinates(monkeypatch):
    monkeypatch.setattr(adapter.runner.e, 'objective', lambda *a:5.)
    args = example()
    assert adapter.saved_preflight(*args)['public_terminal_verified'] is False
    args[1]['baseline_owners']['c0']['point'] = 456
    with pytest.raises(ValueError, match='owner'):adapter.saved_preflight(*args)
    args = example();args[0]['problems']['fitted_c'][1][0]+=1e-6
    with pytest.raises(ValueError, match='endpoint'):adapter.saved_preflight(*args)


def test_saved_baseline_requires_frequency_replay(monkeypatch):
    monkeypatch.setattr(adapter.runner.e, 'objective', lambda *a:6.)
    with pytest.raises(ValueError, match='score'):adapter.saved_preflight(*example())


def test_adapter_does_not_change_candidate_settings():
    frozen = adapter.runner.read(adapter.OUT.parent/'candidate/protocol.json')
    assert adapter.runner.SETTINGS==frozen['settings']
    assert adapter.source_inventory()[str(Path(adapter.__file__))]==adapter.runner.sha(adapter.__file__)
