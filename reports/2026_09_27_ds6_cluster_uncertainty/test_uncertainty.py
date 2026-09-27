import numpy as np
from run_audit import covariance


def test_cluster_covariance_does_not_gain_precision_from_duplicated_data():
    g=np.array([[1,2,-1],[-1,1,2],[3,-2,1],[-3,-1,-2]],dtype=float)
    h=np.diag([5.,6.,7.]);labels=['a','b','c','d']
    original=covariance(g,h,labels)
    duplicated=covariance(np.tile(g,(2,1)),2*h,labels*2)
    assert original['state']==duplicated['state']=='complete'
    np.testing.assert_allclose(original['cluster_covariance'],duplicated['cluster_covariance'])
    np.testing.assert_allclose(np.array(original['model_covariance'])/2,duplicated['model_covariance'])


def test_sandwich_agrees_with_direct_group_sum_and_rejects_invalid_information():
    g=np.arange(24,dtype=float).reshape(8,3)-11.5;labels=[0,0,1,1,2,2,3,3]
    h=np.array([[5.,.5,.3],[.5,6.,.2],[.3,.2,7.]])
    result=covariance(g,h,labels);sums=g.reshape(4,2,3).sum(axis=1);sums-=sums.mean(axis=0)
    expected=np.linalg.solve(h,sums.T)@np.linalg.solve(h,sums.T).T*4/3
    np.testing.assert_allclose(result['cluster_covariance'],expected)
    assert covariance(g,np.diag([1,1,-1]),labels)['state']=='unavailable'
    assert covariance(g,h,[0]*8)['state']=='unavailable'


def test_profiled_horizontal_ellipse_uses_marginal_covariance():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('cluster_uncertainty_summary',Path(__file__).with_name('summarize.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    ellipse,CHI2_95=module.ellipse,module.CHI2_95
    cov=np.array([[4.,0.,1.],[0.,1.,0.],[1.,0.,3.]])
    result=ellipse(cov,np.array([2.,0.]))
    np.testing.assert_allclose(result['major95_m'],2000*np.sqrt(CHI2_95))
    assert result['squared_mahalanobis']==1. and result['reference_inside']
    assert not ellipse(cov,np.array([10.,0.]))['reference_inside']


def test_all43_source_binding_and_covariance_consistency():
    import json
    from run_audit import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(HERE/'run_audit.py')==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(protocol['sessions'])==43
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete'] and result['protocol_sha256']==digest(HERE/'protocol.json')
        tracks=result['tracks'];g=np.array([t['gradient'] for t in tracks]);info=np.array(result['information'])
        assert all(np.isfinite(t['training_map_mass']) and 0<t['training_map_mass']<=1 for t in tracks)
        for name,labels in [('track',[t['track_id'] for t in tracks]),('candidate',[t['candidate_row'] for t in tracks])]:
            assert covariance(g,info,labels)==result['arms'][name]
            if result['arms'][name]['state']=='complete':
                cov=np.array(result['arms'][name]['cluster_covariance'])
                np.testing.assert_allclose(cov,cov.T,atol=1e-10)
                assert np.linalg.eigvalsh(cov).min()>-1e-10
