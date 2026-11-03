import numpy as np
from cross_band import normalized_difference


def test_correct_rf_normalization_preserves_shared_curved_doppler():
    t4=np.linspace(175,210,90);t5=np.linspace(176,199,71)
    curve=lambda t:30000-1700*(t-180)+3*(t-180)**2-.02*(t-180)**3
    ratio=11.7096875/11.4596875
    result=normalized_difference(t4,curve(t4),11.4596875e9,t5,curve(t5)*ratio+8123,11.7096875e9)
    assert result['constant_removed_rms_hz']<1e-7
    assert abs(result['constant_difference_hz']-8123)<1e-7
    wrong=normalized_difference(t4,curve(t4),11.4596875e9,t5,curve(t5)*ratio+8123,11.4596875e9)
    assert wrong['constant_removed_rms_hz']>200
