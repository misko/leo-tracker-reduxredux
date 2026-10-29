from types import SimpleNamespace
import numpy as np
import pytest
from probe_receiver_gap_recovery import witness_entries


def test_witness_append_never_creates_calibration_members_or_reuses_ids():
    scan=SimpleNamespace(tracks=[],white=[],rx_basis=[],curved=[],fixed_window_noise=dict(extra_parameter_BIC_gain=0))
    row=dict(track=dict(key='w',times=[1.,2.,3.,4.],values=[4.,3.,2.,1.],observation_ids=['a','b','c','d']),
        fixed_family_top=[dict(norad=10,candidate_index=0,alias=0)],free_phase_top=[dict(norad=10)])
    changed,entries=witness_entries(scan,[row],set())
    assert not scan.tracks and changed.curved==[] and len(changed.tracks)==1
    assert entries[0]['discovery_only'] and entries[0]['track_index']==0
    np.testing.assert_array_equal(changed.tracks[0]['times'],[1,2,3,4])
    with pytest.raises(ValueError,match='overlap'):witness_entries(scan,[row],{'b'})
    with pytest.raises(ValueError,match='overlap'):witness_entries(scan,[row,row],set())
    scan.fixed_window_noise=dict(extra_parameter_BIC_gain=1,per_observation_noise_sigma_hz={})
    with pytest.raises(ValueError,match='noise'):witness_entries(scan,[row],set())
