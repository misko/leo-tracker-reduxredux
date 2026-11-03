import numpy as np
from ablate_ds23_frequency_event_satellites import removal_mask


def test_satellite_removal_drops_all_its_curved_and_predictive_factors_only():
    rows=[dict(candidate_norad=1,component='A'),dict(candidate_norad=2,component='B'),dict(candidate_norad=1,component='C')]
    slices=[slice(0,2),slice(2,4),slice(4,6)];original=np.array([1,0,1,1,0,1],bool)
    entries=[dict(norad=1,component='linearA'),dict(norad=2,component='linearB')]
    keep,pred=removal_mask(rows,slices,original,entries,[1])
    np.testing.assert_array_equal(keep,[False,False,True,True,False,False])
    assert pred==[entries[1]]
    np.testing.assert_array_equal(original,[1,0,1,1,0,1])


def test_track_removal_preserves_other_tracks_of_the_same_satellite():
    rows=[dict(candidate_norad=1,component='A'),dict(candidate_norad=1,component='B')]
    keep,pred=removal_mask(rows,[slice(0,2),slice(2,4)],np.ones(4,bool),[],components=['A'])
    np.testing.assert_array_equal(keep,[False,False,True,True]);assert pred==[]
