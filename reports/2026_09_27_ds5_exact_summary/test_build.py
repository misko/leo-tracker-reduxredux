import importlib.util,math
from pathlib import Path
spec=importlib.util.spec_from_file_location("b",Path(__file__).with_name("build.py"));assert spec and spec.loader
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
def test_distance_zero_and_known_offset():
    assert B.distance(B.REFERENCE,B.REFERENCE)==0
    assert B.distance((0,0),(0,1))==pytest.approx(111.195,abs=.001)
def test_postseal_scores_only_sealed_inference(tmp_path):
    p=tmp_path/"inference.json";B.write(p,{"schema":"ds5-exact-full42-inference-summary/v1","results":[{"method":"cell","winner":{"latitude_deg":B.REFERENCE[0],"longitude_deg":B.REFERENCE[1],"east_km":0,"north_km":0},"winner_on_edge":False,"objective_name":"weighted_mse_hz2","objective_value":1}]});v=B.postseal(p);assert v["results"][0]["horizontal_error_km"]==0 and v["reference_used_postseal_only"]
import pytest
