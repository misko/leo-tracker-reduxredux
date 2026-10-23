import numpy as np
import run_bias as b

def test_default_reproduces_shared_predictive_density():
    rng=np.random.default_rng(25);raw=rng.normal(0,200,12);design=rng.normal(size=(12,3));gram=np.eye(3)*2
    sigma=np.full(12,110.);groups=np.repeat([0,1],6)
    old=b.original_predictive_residual(raw,design,gram,sigma,groups)
    new=b.predictive_with_bias(raw,design,gram,sigma,groups,[300,300])
    assert abs(old['objective']-new['objective'])<1e-10
    assert np.allclose(old['residual'],new['residual'],rtol=0,atol=1e-12)

def test_only_new_native_paths_change_and_replay():
    result=b.s.read(b.OUT/'results.json')
    for case in result['cases']:
        assert all(abs(r['saved_objective_difference'])<1e-5 for r in case['replay'].values())
        original={e['component'] for e in case['parent_entries']}
        for fit in case['fits']:
            assert fit['original_parent_ids_preserved']
            assert len(fit['summary']['history'])==5
            for e,sigma in zip(case['entries'],fit['configuration']['entry_bias_sigmas_hz'],strict=True):
                assert sigma==(300 if e['component'] in original else fit['native_bias_sigma_hz'])
            if fit['native_bias_sigma_hz']==300:
                assert abs(fit['common_sigma300']['negative_twice_elbo']-fit['summary']['negative_twice_elbo'])<1e-5
                assert abs(fit['summary']['negative_twice_elbo']-case['replay'][fit['arm']]['negative_twice_elbo'])<1e-5
