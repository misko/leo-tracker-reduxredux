import numpy as np
from compare_four_scans import THRESHOLDS, curvature, screen, plot, fitted_residual


def test_residual_uses_loss_geometry_not_delegated_raw_prediction():
    from types import SimpleNamespace
    def forbidden(*args,**kwargs):
        raise AssertionError('raw-row prediction is not family-row prediction')
    data=SimpleNamespace(measured=np.array([105.,210.]),rf=np.array([11.085e9,11.085e9]),predict=forbidden)
    obj=SimpleNamespace(size=2,features=np.array([[1.],[2.]]),likelihood=SimpleNamespace(alias_hz=1000.),
        base=SimpleNamespace(predict=lambda vector:(np.array([[100.],[200.]]),None)))
    residual=fitted_residual(data,obj,dict(vector=[0.,0.,3.],rf_coefficient_hz_per_ghz=[3.]))
    np.testing.assert_allclose(residual,[[2.],[4.]])


def test_threshold_policy_is_strict_frozen_and_retains_unassessed():
    tracks=[dict(catalog_number=1,ratio=1.1),dict(catalog_number=1,ratio=1.11),
            dict(catalog_number=2,ratio=1.025),dict(catalog_number=3,ratio=None)]
    prior={1,2,3,4}
    for cutoff in THRESHOLDS:
        policy=screen([1,2,3,4],tracks,cutoff)
        assert set(policy['kept'])<=prior
        assert policy['unassessed']==[3,4]
        assert {3,4}<=set(policy['kept'])
        prior=set(policy['kept'])
    assert prior=={2,3,4}


def test_curvature_detects_quadratic_not_linear():
    t=np.linspace(-30,30,100)
    noise=np.sin(np.arange(100)*1.4)
    line=curvature(t,3*t+noise)
    quadratic=curvature(t,3*t+.1*t*t+noise)
    assert line['ratio']<1.025
    assert quadratic['ratio']>1.1
    assert curvature(t[:3],noise[:3])['ratio'] is None


def test_plot_and_csv(tmp_path):
    variants=[]
    for cutoff in THRESHOLDS:
        variants.append(dict(threshold=cutoff,status='evaluated',policy=dict(kept=[1,2],unassessed=[2]),
            best=dict(distance_m=1000.,east_m=0.,north_m=-1000.,delta_score=-1.),
            roof_gradient_per_100m=[0.,1.],roof_support=100.,start_agreement_m=.1,
            boundary=False,gradient_check_passed=True))
    plot(tmp_path,dict(scans=[dict(scan_index=1,session='scan-fw-example',variants=variants)]))
    assert (tmp_path/'comparison.png').stat().st_size>1000
    assert len((tmp_path/'summary.csv').read_text().splitlines())==6
