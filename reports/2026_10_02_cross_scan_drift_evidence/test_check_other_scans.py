import numpy as np

from check_other_scans import circular, design, huber_fit, select_pairs


def test_wrap_and_polynomial_units():
    assert abs(circular(227272.72727272726 + 5) - 5) < 1e-9
    t=np.linspace(0,300,100)
    ch=np.tile([1,2],50)
    x=design(t,ch,2,[1,2])
    coefficients=np.array([100.,200.,300.,225.])
    result=huber_fit(x,x@coefficients)
    np.testing.assert_allclose(result,coefficients,atol=1e-7)
    assert abs(result[-2]/150-2)<1e-8
    assert abs(result[-1]/150**2-.01)<1e-8


def test_pair_selection_does_not_use_frequency_difference():
    metadata=[]
    for receiver,margin,offset in [(0,.8,0),(1,.7,.1),(1,.9,.2)]:
        metadata.append(dict(native_residual_bin=0,local_probe_key=[3,receiver,0],integer_session_sample=1000,fractional_epoch_offset_samples=offset,fractional_margin=margin))
    arrays={"rf":np.ones(3)*11e9,"times":np.array([.001,.00100001,.00100002]),"measured":np.array([100.,101.,100000.]),"channel":np.ones(3),"margin":np.array([.8,.7,.9])}
    pairs=select_pairs(metadata,[0,1,2],arrays,1e7,1e-7)
    assert len(pairs)==1
    assert pairs[0]["row1"]==2
    assert pairs[0]["rx1_minus_rx0_raw_hz"]==99900


def test_pair_epoch_and_native_zero_gates():
    metadata=[dict(native_residual_bin=0,local_probe_key=[3,0,0],integer_session_sample=1000,fractional_epoch_offset_samples=0.,fractional_margin=.8),dict(native_residual_bin=1,local_probe_key=[3,1,0],integer_session_sample=1000,fractional_epoch_offset_samples=0.,fractional_margin=.9)]
    arrays={"rf":np.ones(2)*11e9,"times":np.ones(2)*.001,"measured":np.array([100.,101.]),"channel":np.ones(2),"margin":np.array([.8,.9])}
    assert select_pairs(metadata,[0,1],arrays,1e7,1e-7)==[]
    metadata[1]["native_residual_bin"]=0
    metadata[1]["fractional_epoch_offset_samples"]=2
    assert select_pairs(metadata,[0,1],arrays,1e7,1e-7)==[]
