import numpy as np
import pytest

from evaluate import distance, metrics, require_complete
from models import cold, latlon, tile, whole_track_split
from null_guard import decision, shifted
from shape_refinement import refine
from synthetic import line_of_sight, station_geometry


def test_geographic_tile_switch_restores_origin_and_wraps_date_line():
    original = cold.CENTER
    with tile((12.,179.97)):
        assert cold.CENTER == (12.,179.97)
        endpoint = latlon(cold.CENTER, (8.,6.))
        assert endpoint[1] < -179.
        assert distance(cold.CENTER, endpoint) == pytest.approx(10., abs=.03)
    assert cold.CENTER == original


def test_height_and_independent_range_rate_units():
    point=(23.,-77.)
    base, frame=station_geometry(point,0.)
    high,_=station_geometry(point,1.2)
    assert high-base == pytest.approx(1.2*frame[2],abs=1.e-9)
    offset = np.array([[1.,2.,3.]])*500.
    velocity = np.array([[2.,-1.,4.]])
    delta=.01
    plus=np.linalg.norm(offset+delta*velocity,axis=1)
    minus=np.linalg.norm(offset-delta*velocity,axis=1)
    brute=-(plus-minus)/(2*delta)*11.5e9/299792.458
    assert line_of_sight(base+offset,velocity,base,11.5e9) == pytest.approx(brute,rel=1.e-8)


def test_whole_track_time_holdout_excludes_crossing_tracks():
    graph = dict(tracks=[{"times":np.array(t)} for t in ([1.,149.],[151.,170.],[140.,155.])],
                 curved_indices=[0,1,2])
    before,after=whole_track_split(graph)
    assert before["curved_indices"]==[0]
    assert after["curved_indices"]==[1]


def test_refinement_improves_off_lattice_score_and_obeys_box():
    true = np.array([1.2,-1.7])
    score = lambda xy: -np.sum((xy-true)**2,axis=1)
    pos=refine([0.,0.],4.,12.5,score)
    assert np.linalg.norm(pos-true) < .18
    edge=refine([12.5,0.],4.,12.5,lambda xy:xy[:,0])
    assert np.array_equal(edge,[12.5,0.])


def test_counts_failures_against_all_attempts_and_rejects_duplicate_cases():
    data=dict(method="m",arm="c0",rms_hz=None,clean_assigned=None,correct_clean_ids=None)
    measured=metrics([dict(data,error_km=1.),dict(data,error_km=None)])["m"]["c0"]
    assert measured["attempts"]==2 and measured["within_5km"]==1 and measured["geo_km"]["n"]==1
    with pytest.raises(ValueError):
        require_complete([{"case":"a"},{"case":"a"}],("case",),[("a",),("b",)])


def test_null_guard_competes_across_all_regions_and_requires_a_strict_win():
    win = [.80]+[.50]*19
    decoy = [.71]+[.60]*19
    assert decision({"first":win,"second":decoy})["accepted"]
    decoy[4] = .80
    assert not decision({"first":win,"second":decoy})["accepted"]
    assert not decision({"empty":[None]*20})["accepted"]
    graph = {"tracks":[{"times":[151.,155.,167.], "values":[5.,6.,7.]}],"curved_indices":[0]}
    for i in (1,10,19):
        q=shifted(graph,300.,i)["tracks"][0]
        assert q["values"]==graph["tracks"][0]["values"]
        assert np.diff(q["times"])==pytest.approx(np.diff(graph["tracks"][0]["times"]))
        assert 150.<=q["times"][0]<q["times"][-1]<=300.
