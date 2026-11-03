import importlib.util,json,sys
from pathlib import Path
import numpy as np,pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("extend_orbits",HERE/"extend_orbits.py"); assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=module;SPEC.loader.exec_module(module)


def test_plan_preserves_cadence_and_expands_four_knot_query_bounds():
    old=np.arange(-10.,21.,5.); plan=module.plan_extension(old,120.)
    assert plan["added_knots_per_side"]==24
    assert np.array_equal(plan["times_s"][24:-24],old)
    assert np.all(np.diff(plan["times_s"])==5.)
    assert plan["old_query_bounds_s"]==[-5.,15.]
    assert plan["new_query_bounds_s"]==[-125.,135.]


def test_plan_rejects_nonuniform_or_too_short_grids():
    with pytest.raises(ValueError,match="four knots"): module.plan_extension([0,5,10])
    with pytest.raises(ValueError,match="uniform"): module.plan_extension([0,5,11,16])


def test_binding_verification_detects_mutation(tmp_path):
    observation=tmp_path/"observation.json";observation.write_text(json.dumps({"session_id":"S","start_utc_ns":10}))
    state=tmp_path/"state.npz";np.savez(state,x=np.array([1]))
    tle=tmp_path/"archive"/"source"/"1-x.tle";tle.parent.mkdir(parents=True);tle.write_text("tle")
    metadata=tmp_path/"metadata.json";metadata.write_text(json.dumps({"session_id":"S","observation_sha256":module.digest(observation),
        "state_sha256":module.digest(state),"tle":{"path":str(tle),"sha256":module.digest(tle),"causal":True}}))
    module.verify_bindings(observation,metadata,state)
    tle.write_text("changed")
    with pytest.raises(ValueError,match="tle binding mismatch"):module.verify_bindings(observation,metadata,state)


def test_finite_error_free_radius_crossing_is_diagnostic_not_rejection():
    position=np.array([[[6498.2,0,0],[6498.1,0,0]]]);velocity=np.ones_like(position)
    rows=module._validate_propagation(np.zeros((1,2),dtype=int),position,velocity,[53480],[0.,5.])
    assert rows[0]["norad_id"]==53480 and rows[0]["crossing_times_s"]==[5.]


def test_sgp4_error_or_nonfinite_state_remains_fatal():
    position=np.ones((1,2,3))*7000;velocity=np.ones_like(position)
    with pytest.raises(ValueError,match="53480"):module._validate_propagation(np.array([[0,6]]),position,velocity,[53480],[0.,5.])
    position[0,1,0]=np.nan
    with pytest.raises(ValueError,match="finite.*False"):
        module._validate_propagation(np.zeros((1,2),dtype=int),position,velocity,[53480],[0.,5.])
