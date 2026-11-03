"""Execution options must preserve explicit recorded-replay choices."""
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('recorded_protocol',Path(__file__).resolve().parents[3]/'tools/run_recorded_pacing.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_execution_flags():
    assert module.execution_flags({})==[]
    assert module.execution_flags({'probe_prefix_only':False,'iq_reuse':False})==[]
    assert module.execution_flags({'probe_prefix_only':True,'iq_reuse':True})==['--probe-prefix','--reuse-iq']


@pytest.mark.parametrize('key',['probe_prefix_only','iq_reuse'])
@pytest.mark.parametrize('value',['false',1,None])
def test_reject_non_boolean(key,value):
    with pytest.raises(ValueError,match='invalid boolean'):
        module.execution_flags({key:value})
