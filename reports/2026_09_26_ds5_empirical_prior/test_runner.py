import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np

spec=importlib.util.spec_from_file_location('empirical_ds5_runner',Path(__file__).with_name('run_ds5.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def test_coarse_shortlist_is_training_only_and_site_local(monkeypatch):
    measured=np.array([0.,1.,100.,200.]);mask=np.array([True,True,False,False])
    prepared=SimpleNamespace(catalogue=object(),candidate_indices=[0,1,2,3],start_utc_ns=0,
        tracks=[SimpleNamespace(track_id='track')])
    monkeypatch.setattr(runner,'build_prediction_banks',lambda *a,**kw:(None,None))
    monkeypatch.setattr(runner,'point_factory',lambda lat,lon:lat)
    def evaluator(banks,site,taus_s):
        scores=[0,1,2,3] if site==0 else [3,2,1,0]
        pred=np.array([[[0.,1.+s,9999.,-9999.] for _ in taus_s] for s in scores])
        block=SimpleNamespace(track_id='track',training_mask=mask,measured_hz=measured,
            predictions_hz=pred,visible=np.ones(4,bool),candidate_ids=[10,20,30,40])
        return lambda *args:[block]
    monkeypatch.setattr(runner,'RegionalTrackPredictionEvaluator',evaluator)
    sites={'a':{'latitude_deg':0,'longitude_deg':0},'b':{'latitude_deg':1,'longitude_deg':0}}
    first=runner.shortlist(prepared,sites,{})
    assert [r['candidate_id'] for r in first['a']['track']]==['10','20','30']
    assert [r['candidate_id'] for r in first['b']['track']]==['40','30','20']
    measured[~mask]=[-1e9,1e9]
    assert first==runner.shortlist(prepared,sites,{})
