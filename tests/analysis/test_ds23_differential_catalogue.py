from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_differential_catalogue import pair_screen


def test_ordered_satellite_pair_is_identified_with_independent_phase_tangents():
    t=np.linspace(-1,1,40)
    f=np.array([10000+2000*t+300*t*t,-20000+1000*t-500*t*t,40000-3000*t+1500*t*t])
    d=np.array([10+2*t,20-3*t,40+10*t]);widths=np.ones(3)
    y=f[1]-f[0]+.2*d[1]-.1*d[0]+25
    r=pair_screen(y,f,d,widths,5.)
    k=int(np.argmin(r['cost']))
    assert (r['first'][k],r['second'][k])==(0,1)
    assert np.isinf(r['cost'][r['first']==r['second']]).all()


def test_common_receiver_frequency_shift_cancels_from_differential_nomination():
    t=np.linspace(-1,1,40);f=np.array([1000*t+200*t*t,-1000*t-300*t*t])
    d=np.array([10+2*t,20-3*t]);one=pair_screen(f[1]-f[0],f,d,np.ones(2),5.)
    shifted=f+123456.
    two=pair_screen(shifted[1]-shifted[0],shifted,d,np.ones(2),5.)
    np.testing.assert_allclose(one['cost'],two['cost'])
