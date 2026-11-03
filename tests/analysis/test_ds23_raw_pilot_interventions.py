from types import SimpleNamespace
import numpy as np
import pytest
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from local_pilot_refinement import pilot_wave
from probe_native_code_carrier import interpolate_periodic
from probe_ds23_refined_curve_position import update_values
from replay_ds23_archived_pilot_scores import reconstruct


def row(boundary=False):
    return dict(point={'observation_id':'a'},archived_CFO_hz=100.,
        fixed_epoch_CFO=dict(CFO_hz=112.,frequency_search_boundary=boundary))


def test_raw_update_preserves_alias_lift_membership_and_falls_back_at_boundary():
    track=dict(observation_ids=['a','b'],values=np.array([100+2*PERIOD,55.]))
    s=SimpleNamespace(tracks=[track]);r=update_values(s,[row()], 'fixed_epoch_CFO')
    np.testing.assert_allclose(s.tracks[0]['values'],[112+2*PERIOD,55.])
    assert list(r['changed_observation_ids_and_delta_hz'])==['a']
    s.tracks[0]['values'][0]=100+2*PERIOD
    r=update_values(s,[row(True)], 'fixed_epoch_CFO')
    assert s.tracks[0]['values'][0]==100+2*PERIOD
    assert r['original_CFO_fallbacks']=={'a':'frequency boundary'}


def test_raw_update_rejects_a_different_original_peak():
    s=SimpleNamespace(tracks=[dict(observation_ids=['a'],values=[90.])])
    with pytest.raises(ValueError,match='canonical original peak'):
        update_values(s,[row()],'fixed_epoch_CFO')


def test_reconstructs_missing_acquired_CFO_without_changing_archived_tracking_CFO():
    fs=2500000;n=np.arange(fs//50);epoch=123.25;frequency=120123.
    y=interpolate_periodic(pilot_wave(fs,'lower'),(n-epoch)*32)*np.exp(2j*np.pi*frequency*n/fs)
    original=conditioned_glrt64_score(y,fs,epoch_sample=123,fractional_epoch_offset_samples=.25,
                                     acquired_cfo_hz=frequency-450,edge='lower')
    assert abs(original.residual_cfo_hz)>400
    peak=dict(integer_epoch_sample=123,fractional_epoch_offset_samples=.25,
        fractional_tracking_cfo_hz=original.tracking_cfo_hz,
        fractional_exact_score=original.exact_score,fractional_control_score=original.control_score)
    result=reconstruct(y,fs,'lower',peak)
    assert result['matched'] and result['selected']['bin']==1
    assert abs(result['selected']['acquired_CFO_hz']-(frequency-450))<1e-7
