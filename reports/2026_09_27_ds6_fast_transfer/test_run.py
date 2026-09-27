import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location("r",Path(__file__).with_name("run.py"));assert spec and spec.loader
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
def test_haversine_zero_and_degree():
    assert R.haversine((1,2),(1,2))==0
    assert R.haversine((0,0),(0,1))==pytest.approx(111.195,abs=.001)
def test_unit_counts_match_frozen_ds6():
    rows=R.unit_rows(R.load(R.UNITS));assert sum(r["scope"]=="single" for r in rows)==43 and sum(r["scope"]=="group8" for r in rows)==5 and sum(r["scope"]=="full" for r in rows)==1
