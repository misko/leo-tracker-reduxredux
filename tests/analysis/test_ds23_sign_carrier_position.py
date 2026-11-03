from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_sign_carrier_position import intervene
from leo.analysis.research.retained_track_likelihood import PERIOD


def fixture():
    scan=SimpleNamespace(tracks=[dict(values=np.array([100.,200.]),observation_ids=['a','b']),
        dict(values=np.array([100.-PERIOD]),observation_ids=['a'])],radio_sigma_hz=80.,
        fixed_window_noise=dict(extra_parameter_BIC_gain=1.,per_observation_noise_sigma_hz={'a':70.,'b':90.}))
    row=dict(observation_id='a',archived_CFO_hz=100.,proposed_CFO_hz=110.,
        base_fit=dict(CFO_hz=107.),proposed_noise_sigma_hz=5.)
    return scan,row


def test_refinement_updates_all_views_but_preserves_input_ids_and_other_measurements():
    scan,row=fixture();changed,noise,delta=intervene(scan,[row],'sign_CFO_and_precision')
    np.testing.assert_array_equal(scan.tracks[0]['values'],[100.,200.])
    np.testing.assert_array_equal(changed.tracks[0]['values'],[110.,200.])
    np.testing.assert_allclose(changed.tracks[1]['values'],[110.-PERIOD])
    assert changed.tracks[0]['observation_ids']==scan.tracks[0]['observation_ids']
    assert noise=={'a':5.} and delta=={'a':10.}


def test_continuous_control_changes_same_points_without_precision_override():
    scan,row=fixture();changed,noise,delta=intervene(scan,[row],'continuous_same_points')
    np.testing.assert_array_equal(changed.tracks[0]['values'],[107.,200.])
    assert noise=={} and delta=={'a':7.}


def test_noncanonical_rf_value_fails_instead_of_replacing_a_different_peak():
    scan,row=fixture();row['archived_CFO_hz']=101.
    with pytest.raises(ValueError,match='canonical'):intervene(scan,[row],'sign_CFO_only')
