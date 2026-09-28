import pytest
from score_direction_control import ARMS,winners


def test_direction_control_reorders_only_saved_points():
    points=[dict(east_km=e,north_km=0,scores={a:(e if a!='D_plus_reversed_geometry' else -e) for a in ARMS}) for e in (-1.,1.)]
    result=winners(points)
    assert result['D_plus_geometry'] is points[0]
    assert result['D_plus_reversed_geometry'] is points[1]


def test_invalid_control_is_not_silently_ranked():
    with pytest.raises(ValueError,match='empty'):winners([])
    with pytest.raises(ValueError,match='nonfinite'):
        winners([dict(east_km=0,north_km=0,scores={a:float('nan') for a in ARMS})])
