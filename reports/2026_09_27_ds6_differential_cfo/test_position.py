"""Check joint scan timing integration with a physically shared baseline sign."""
import importlib.util
from pathlib import Path
import itertools
import json
import hashlib

import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('position_test',HERE/'position.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_shared_sign_matches_explicit_joint_time_enumeration():
    rng=np.random.default_rng(18)
    scans=[dict(train=rng.normal(size=(2,3)),phase_all=rng.normal(size=(2,3)),cfo_all=rng.normal(size=(2,3)),cfo_train=rng.normal(size=3),cfo_joint=rng.normal(size=3)) for _ in range(2)]
    result=module.combine(scans)
    def direct(field):
        return logsumexp([sum(s[field][sign,t] for s,t in zip(scans,ts))
                          for sign in [0,1] for ts in itertools.product(range(3),repeat=2)])-np.log(18)
    np.testing.assert_allclose(result['phase_train'],direct('train'),atol=1e-12)
    np.testing.assert_allclose(result['held_phase'],direct('phase_all')-direct('train'),atol=1e-12)
    np.testing.assert_allclose(result['phase_held_cfo'],direct('cfo_all')-direct('train'),atol=1e-12)


def test_one_scan_joint_score_matches_existing_uncertainty_model():
    rng=np.random.default_rng(19)
    banks=[dict(y=np.array([.2,.4,.5,.7]),mask=np.array([True,False,True,False]),
                geometry=rng.normal(size=(3,4,4)),cfo_train=rng.normal(size=(3,4)),cfo_joint=rng.normal(size=(3,4))-3) for _ in range(2)]
    kappa=np.geomspace(.1,100,21);weights=np.ones(21)/21
    old=module.u.score_banks(banks,kappa,weights)
    new=module.combine([module.components(banks,kappa,weights)])
    for a,b in [('training_log_evidence','phase_train'),('held_phase_log_predictive','held_phase'),('held_cfo_log_predictive','phase_held_cfo'),('cfo_only_held_log_predictive','cfo_only_held')]:
        np.testing.assert_allclose(old[a],new[b],atol=1e-12)


def test_completed_search_selects_training_maxima_and_reports_boundaries():
    result=json.loads((HERE/'position-results.json').read_text())
    protocol=json.loads((HERE/'position-protocol.json').read_text())
    assert result['complete']
    assert result['protocol_sha256']==hashlib.sha256((HERE/'position-protocol.json').read_bytes()).hexdigest()
    for arm,best in result['best'].items():
        assert best[arm+'_train']==max(p[arm+'_train'] for p in result['points'])
        assert isinstance(best['boundary'],bool)
        if best['refinements']==0:
            assert best['boundary']
            assert max(abs(best['east_km']),abs(best['north_km']))==protocol['local_limit_km']
