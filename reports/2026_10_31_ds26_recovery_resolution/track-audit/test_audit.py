import numpy as np
from audit import train_feature
from cross_channel import fit_scalar


def test_mechanism_fit_does_not_use_held_response_or_feature_preprocessing():
    train=np.array([1,1,1,1,0,0],bool);held=~train
    feature=np.array([0,1,2,3,4,5.]);y=2*feature+1
    a=train_feature(y,feature,train,held)
    changed=y.copy();changed[held]=1e6
    b=train_feature(changed,feature,train,held)
    np.testing.assert_array_equal(a['coefficient_hz'],b['coefficient_hz'])
    assert a['training_feature_mean']==feature[train].mean()
    assert a['training_feature_sd']==feature[train].std()


def test_cross_channel_coefficient_is_not_a_track_offset_detector():
    epoch=np.array([-1.,-.5,.2,.7,1.])
    centered=epoch-epoch.mean()
    a=[dict(epoch=epoch,residual_hz=20*centered),dict(epoch=epoch,residual_hz=20*centered)]
    b=[dict(epoch=epoch,residual_hz=20*centered+1000),dict(epoch=epoch,residual_hz=20*centered-500)]
    np.testing.assert_allclose(fit_scalar(a),fit_scalar(b),rtol=0,atol=1e-10)


def test_existing_glrt_reports_grid_argmax_for_off_bin_noiseless_tone():
    from leo.analysis.starlink.fast_scan_scores import _SymbolCorrelations,_glrt_pair
    from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
    times=(np.arange(64)*OFDM_SYMBOL_DURATION_S)[None,:]
    spacing=1/(512*OFDM_SYMBOL_DURATION_S)
    control=_SymbolCorrelations(np.zeros_like(times,dtype=complex),np.zeros_like(times),times)
    for fraction,expected_bin in ((.1,0),(.4,0),(.6,1)):
        exact=_SymbolCorrelations(np.exp(2j*np.pi*fraction*spacing*times),np.ones_like(times),times)
        (_,frequency),_=_glrt_pair(exact,control,size=512)
        np.testing.assert_allclose(frequency,expected_bin*spacing,rtol=0,atol=1e-9)
