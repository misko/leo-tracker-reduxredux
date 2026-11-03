import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('overlap_semantics_test',Path(__file__).with_name('run.py'))
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_partial_overlap_is_connected_without_equal_support():
    support={'a':{1,2},'b':{2,3},'c':{3,4},'d':{5}}
    assert run.components(support)==[['a','b','c'],['d']]
    assert all(support[a]!=support[b] for a,b in [('a','b'),('b','c')])
