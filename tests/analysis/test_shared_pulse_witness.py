import numpy as np
import pytest
from shared_pulse_witness import fit_pulse,pulse_prediction


def test_recovers_shared_event_despite_independent_curve_constants():
    t=np.arange(0.,30.,.5);pulse=230*((t>=12)&(t<18))
    witnesses=[dict(component=str(i),times_s=t,residual_hz=pulse+b) for i,b in enumerate((-80,140))]
    result=fit_pulse(witnesses,(0,29.5))
    assert result['start_s']==12 and result['end_s']==18
    assert result['amplitude_hz']==pytest.approx(230,rel=.02)
    np.testing.assert_array_equal(pulse_prediction([11,12,18],result),[0,result['amplitude_hz'],0])
    assert result['penalized_gain']>0 and len(result['supported_components'])==2


def test_rejects_single_curve_evidence():
    with pytest.raises(ValueError,match='two witness'):
        fit_pulse([dict(component='one',times_s=np.arange(20.),residual_hz=np.zeros(20))],(0,19))
