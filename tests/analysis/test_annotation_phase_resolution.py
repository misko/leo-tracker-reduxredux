import copy
import pytest
from audit_annotation_phase_resolution import near_threshold, matched_geometry


def sample():
    arm=dict(endpoint_east_north_km=[1.,2.],training_objective=30.,history=[{'success':True}],score=4.)
    return dict(track_id='t',folds=[dict(seed=1,split={'held':[2]},proposals=[dict(norad=10,alias=0,arms={'c0':arm})])])


def test_both_sides_of_threshold_selected_without_position_information():
    assert near_threshold(dict(minimum_margin=9.))
    assert near_threshold(dict(minimum_margin=10.01))
    assert not near_threshold(dict(minimum_margin=13.))
    assert not near_threshold({})


def test_quadrature_may_change_prediction_but_not_training_or_candidates():
    original=sample();refined=copy.deepcopy(original)
    refined['folds'][0]['proposals'][0]['arms']['c0']['score']=5.
    assert matched_geometry(original,refined)
    refined['folds'][0]['proposals'][0]['arms']['c0']['endpoint_east_north_km']=[2.,3.]
    with pytest.raises(ValueError,match='calibration changed'):matched_geometry(original,refined)
    refined=copy.deepcopy(original);refined['folds'][0]['proposals'][0]['norad']=20
    with pytest.raises(ValueError,match='candidate sets'):matched_geometry(original,refined)
