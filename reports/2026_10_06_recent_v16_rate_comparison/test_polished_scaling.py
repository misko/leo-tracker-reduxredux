"""Explicit real-corpus verification of the matched scaling-polish experiment."""
import json
import numpy as np
import pytest
import scaled_optimizer_trial as pilot
import factorial as study


@pytest.mark.real_corpus
def test_polished_scaling_preserves_constraints_and_unscaled_success():
    for arm in study.stage.ARMS:
        signatures=[]
        for mode in ('ordinary','per-window'):
            source=pilot.OUT/f'{arm}-{mode}.json'
            old=json.loads(source.read_text())
            result=json.loads((pilot.OUT/'polished'/source.name).read_text())
            assert result['signature']['source_sha256']==study.stage.sha(source)
            assert result['signature']['maximum_fisher_s']==10.
            metrics=result['metrics']
            assert metrics['objective']<=old['after']['objective']+1e-7
            assert metrics['converged']==(metrics['kkt']<=1e-3)
            assert np.linalg.norm(result['best']['point_km'])<=4.+1e-7
            assert np.max(abs(np.asarray(result['best']['parameters'][6:])))<=20.+1e-7
            if arm=='zero-c':assert abs(result['best']['coefficient'])<1e-12
            signatures.append(old['signature']['input_sha256'])
        assert signatures[0]==signatures[1]
