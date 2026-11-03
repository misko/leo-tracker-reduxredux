from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from inventory_ds23_cross_RX_curves import identify_peak,native_fragments
from ds23_frame_registration import PERIOD


def test_an_active_winner_is_never_renamed_as_an_extra_measurement():
    row=dict(channel=1,rf_hz=11e9,time_s=1.)
    original=dict(observation_id='a',measured_cfo_hz=100.)
    assert identify_peak('case',1,row,dict(epoch=0,cfo=100.+PERIOD),original,{'a'})==(None,'already_active')
    assert identify_peak('case',1,row,dict(epoch=0,cfo=100.),original,set())==('a','unretained_original')
    assert identify_peak('case',1,row,dict(epoch=0,cfo=200.),original,set())==(None,'unresolved_neighboring_peak')


def test_curvature_cannot_be_created_by_linking_long_separated_short_fragments():
    t=np.r_[np.arange(6.),100+np.arange(6.)]
    rows=[dict(time_s=float(x),native_CFO_hz=float(10*x*x)) for x in t]
    assert native_fragments(rows,150.)==[]


def test_linear_native_points_never_become_calibration():
    t=np.arange(40.)
    rows=[dict(time_s=float(x),native_CFO_hz=float(100+50*x)) for x in t]
    assert native_fragments(rows,150.)==[]


def test_recovered_winner_keeps_original_noise_in_dormant_and_active_rows():
    from probe_ds23_cross_RX_curves_position import add_native_noise
    noise=dict(per_observation_noise_sigma_hz={'original':113.})
    add_native_noise(noise,['original','new-native'],150.)
    assert noise['per_observation_noise_sigma_hz']=={'original':113.,'new-native':150.}
