import pytest
from audit_continuation import changes


def test_state_changes_include_clutter_and_satellite_alternatives():
    r=changes([[.9,0],[.8,.1],[.1,.1],[.7,.2]],
              [[0,.9],[.1,.1],[.8,.1],[.7,.2]])
    assert r['windows']==4 and r['most_probable_state_changed']==3
    assert r['satellite_to_other_satellite']==1
    assert r['satellite_to_clutter']==1 and r['clutter_to_satellite']==1
    assert r['mean_total_variation']>0


def test_identical_responsibilities_and_invalid_mass():
    assert changes([[.3,.2]],[[.3,.2]])['mean_total_variation']==0
    with pytest.raises(ValueError):changes([[.9,.9]],[[.3,.2]])
