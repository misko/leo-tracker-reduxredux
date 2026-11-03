import numpy as np
import pytest
from ds23_frame_clock_comparison import compare_clock_curvature


@pytest.mark.parametrize('sign',[-1.,1.])
def test_signed_geometric_delay_is_identified_after_affine_clock_removal(sign):
    time=np.arange(60)*.2;rho=900+.05*time*time
    arrival=time+sign*rho/299792.458+17e-6+3e-6*time
    rows=compare_clock_curvature(time,arrival,rho)
    assert len(rows)==1
    assert rows[0]['gamma']==pytest.approx(sign,abs=1e-7)
    key='positive_range_RMS_us' if sign>0 else 'negative_range_RMS_us'
    assert rows[0][key]<1e-7
