import numpy as np
import pytest
from prepare_algo03_catalogue72 import older_candidate,append_bank
from probe_algo03_catalogue72_screen import competitive


def test_age_extension_never_admits_future_or_already_eligible_elements():
    hour=3600_000_000_000;cutoff=100*hour
    assert older_candidate(cutoff-72*hour,cutoff)
    assert older_candidate(cutoff-49*hour,cutoff)
    assert not older_candidate(cutoff-48*hour,cutoff)
    assert not older_candidate(cutoff-73*hour,cutoff)
    assert not older_candidate(cutoff+hour,cutoff)


def test_append_preserves_original_state_bits_and_catalogue_indices():
    original=dict(time_s=np.array([0.,1.]),position_km=np.arange(6.).reshape(1,2,3),
        velocity_km_s=np.ones((1,2,3)),norad=np.array([1]),phase_sigma_s=np.array([1.]))
    result=append_bank(original,np.zeros((1,2,3)),np.zeros((1,2,3)),[2])
    for k in ('position_km','velocity_km_s','norad','phase_sigma_s'):
        np.testing.assert_array_equal(result[k][:1],original[k])
    np.testing.assert_array_equal(result['time_s'],original['time_s'])
    with pytest.raises(ValueError,match='unique'):
        append_bank(original,np.zeros((1,2,3)),np.zeros((1,2,3)),[1])


def test_expanded_catalogue_cannot_force_ambiguous_or_different_c_arm_labels():
    candidate=dict(candidate_index=101,alias=0,noise_screen_pass=True,RMS_hz=40.,bias_hz=20.,phase_s=1.)
    row=dict(candidates=[candidate],gap_to_second=20.)
    assert competitive(row,row,100,110)
    assert not competitive(dict(row,gap_to_second=1.),row,100,110)
    assert not competitive(dict(row,candidates=[dict(candidate,candidate_index=99)]),row,100,110)
    assert not competitive(dict(row,candidates=[dict(candidate,alias=1)]),row,100,110)
