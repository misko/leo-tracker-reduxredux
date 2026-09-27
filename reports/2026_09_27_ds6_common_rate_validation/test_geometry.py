"""Numerical safeguards for conditional phase/association comparisons."""
import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('validation_geometry',Path(__file__).with_name('geometry.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def banks():
    rng=np.random.default_rng(11)
    return [dict(y=np.array([.2,.5,.3,.8]),mask=np.array([True,False,True,False]),
                 geometry=rng.normal(size=(3,4,4)),cfo_train=rng.normal(size=(3,4)),
                 cfo_joint=rng.normal(size=(3,4))-4.) for _ in range(2)]


def test_response_only_cannot_change_cfo_prediction():
    result=module.score_banks(banks(),False)
    assert abs(result['held_cfo_log_predictive']-result['cfo_only_held_log_predictive'])<1e-12


def test_held_phase_cannot_change_training_or_cfo_prediction():
    original=banks();changed=[dict(b,y=b['y']+np.where(b['mask'],0.,1.3)) for b in original]
    a,b=module.score_banks(original),module.score_banks(changed)
    assert a['training_log_evidence']==b['training_log_evidence']
    assert a['held_cfo_log_predictive']==b['held_cfo_log_predictive']
    assert a['held_phase_log_predictive']!=b['held_phase_log_predictive']


def test_phase_wrap_invariance():
    original=banks();changed=[dict(b,geometry=b['geometry']+2*np.pi) for b in original]
    a,b=module.score_banks(original),module.score_banks(changed)
    for key in a:assert abs(a[key]-b[key])<1e-12
