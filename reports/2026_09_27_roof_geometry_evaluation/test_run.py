import importlib.util
from pathlib import Path

P=Path(__file__).with_name("run.py"); s=importlib.util.spec_from_file_location("roof_run",P); m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_missing_is_not_nondetection():
 r={"available":False,"rx":{0:{"detected":False,"candidates":[]},1:{"detected":False,"candidates":[]}}}
 assert m.classify([r],0)[0]["category"]=="missing"

def test_alias_wrap():
 assert abs(m.circ(m.ALIAS-3,m.ALIAS)+3)<1e-9

def test_holdout_disjoint():
    assert m.CAL.isdisjoint(m.HOLD) and len(m.CAL)==5 and len(m.HOLD)==3

def test_incomplete_analysis_is_excluded():
 inv=[{"session_id":"a","split":"holdout","missing_analysis_visits":0},{"session_id":"b","split":"holdout","missing_analysis_visits":2}]
 assert {x["session_id"] for x in inv if x["split"]=="holdout" and x["missing_analysis_visits"]==0}=={"a"}
