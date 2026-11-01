import pytest
from leo.contracts.fast_graph_position_v5 import MODEL_VERSION
from leo.storage.graph_position_lookup_v5 import FastGraphPositionLookupV5,GraphPositionLookupV5,completed_view

def terminal():
    position=dict(latitude_deg=37.,longitude_deg=-122.)
    arms={a:dict(endpoint_latlon=[37.,-122.]) for a in ('c0','fitted_c')}
    v1=dict(model_version='algo02-causal-family-v1',state='complete',position=position,arms=arms)
    v2=dict(model_version='algo03-causal-predictive-v1',state='complete',position=position,baseline=v1,
            selected=dict(arms=arms),decision='ALGO03_single',baseline_seconds=1)
    v3=dict(model_version='algo04-causal-numerical-v1',state='complete',position=position,incumbent=v2,
            candidate=v2,decision='ALGO04_additive',numerical_seconds=1)
    v4=dict(model_version='algo05-causal-gap-conditional-v1',state='complete',position=position,incumbent=v3,
            candidate=dict(trial=dict(arms=arms)),decision='ALGO05_additive')
    return dict(model_version=MODEL_VERSION,state='complete',position=position,incumbent=v4,
                candidate=dict(trial=dict(arms=arms)),decision='ALGO06_additive',
                incumbent_seconds=3,recovery_seconds=2,total_seconds=5)

def test_completed_result_does_not_enumerate_historical_inputs():
    saved=terminal()
    class Lookup:
        def completed_run(self,run):assert run=='scan';return saved
    class Forbidden:
        def detail(self,_):raise AssertionError('Historical lookup must not run')
    v=GraphPositionLookupV5('.',MODEL_VERSION,lookup=Lookup(),previous=Forbidden())
    value=v.detail('scan')
    assert value['position']==saved['position'] and value['selected']['model_version']==MODEL_VERSION
    assert value['baseline']['model_version']=='algo02-causal-family-v1'
    assert not value['fallback'] and value['incumbent']['model_version']=='algo03-causal-predictive-v1'

def test_fallback_projects_actual_prior_model():
    saved=terminal();saved.update(candidate=None,decision='ALGO05_fallback',position=saved['incumbent']['position'])
    value=completed_view('scan',saved)
    assert value['fallback'] and value['selected']['model_version']=='algo05-causal-gap-conditional-v1'
    assert value['position']==saved['incumbent']['position']

def test_lookup_validates_terminal_and_rejects_wrong_identity(tmp_path,monkeypatch):
    store=FastGraphPositionLookupV5(tmp_path)
    p=store.path('job');p.mkdir(parents=True);(p/'status.json').write_text('{}')
    job=dict(job_id='job',run_id='scan',model_version=MODEL_VERSION,state='complete')
    monkeypatch.setattr(store,'status',lambda _:job)
    def corrupt(_):raise ValueError('Changed incumbent')
    monkeypatch.setattr(store,'terminal',corrupt)
    assert store.completed_run('scan') is None
    monkeypatch.setattr(store,'terminal',lambda _:(terminal(),{}))
    assert store.completed_run('scan')['decision']=='ALGO06_additive'
    job['job_id']='different'
    assert store.completed_run('scan') is None
    with pytest.raises(ValueError):store.completed_run('../escape')
