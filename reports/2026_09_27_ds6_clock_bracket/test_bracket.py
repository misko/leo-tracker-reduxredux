import pytest
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('ds6_clock_bracket',Path(__file__).with_name('run.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
bracket=module.bracket


def test_bracket_preserves_integer_nanosecond_offsets():
    start=1790465417939110502
    d=dict(start_utc_ns=start,timing=dict(qualified=True,first_sample_estimate_utc_ns=start,
        first_sample_earliest_utc_ns=start-181544415,first_sample_latest_utc_ns=start+181544415))
    assert bracket(d)==(-.181544415,.181544415)
    d['timing']['qualified']=False
    with pytest.raises(AssertionError):bracket(d)
