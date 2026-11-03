import numpy as np
import pytest
from ds23_joint_relative_position import column_map


def test_original_coefficient_slots_are_shared_and_new_coordinates_appended():
    r=column_map([10,20],[20],8,18,[20,30],[20,30],2)
    np.testing.assert_array_equal(r['mapping'],[9,18,10,11,12,19,20,21,22,23])
    assert r['width']==24 and r['new_phases']=={30:18} and r['new_modes']=={30:19}


def test_rf_ownership_cannot_change_existing_orbit_prior_support():
    with pytest.raises(ValueError,match='silently enable'):
        column_map([10,20],[20],8,18,[10,20],[10,20],1)


def test_original_only_phase_coordinates_remain_available_to_GLRT():
    r=column_map([10,20,40],[40],5,16,[20,30],[],1)
    np.testing.assert_array_equal(r['mapping'],[6,16,17])
    assert r['width']==18
