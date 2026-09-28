import pytest
from local_grid_reporting import compare


def point(e,d,j):
    return dict(east_km=e,north_km=0,latitude_deg=0,longitude_deg=e/111.,scores={'D':d,'D_plus_geometry':j})


def test_reports_refinement_separately_from_geometry():
    points=[point(3,3,3),point(2,1,2),point(1,2,1)]
    result=compare(points,points[0],(0,0))
    assert result['selected']['D']['east_km']==2
    assert result['selected']['D_plus_geometry']['east_km']==1
    assert result['refinement_change_km']<0 and result['geometry_ranking_change_km']<0


def test_comparison_requires_identical_unique_inventory_containing_seed():
    seed=point(0,1,1)
    with pytest.raises(ValueError,match='duplicate'):compare([seed,seed],seed,(0,0))
    with pytest.raises(ValueError,match='omits'):compare([point(1,2,2)],seed,(0,0))


def test_ties_do_not_use_reference_error():
    points=[point(1,1,1),point(-1,1,1)]
    result=compare(points,points[0],(0,1/111.))
    assert result['selected']['D']['east_km']==-1
