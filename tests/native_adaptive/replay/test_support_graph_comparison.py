import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('support_compare',
    Path(__file__).resolve().parents[3]/'tools/compare_native_support_graph.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

HEADER = 'META\tscan\tsha256:abc\t100\n' \
         'candidate_id\tstart_utc_ns\tcenter_utc_ns\tend_utc_ns\tm0\tm1\tm2\tm3\n'
ROW = 'cid\t100\t110\t120\t1\t0\t0.00001\t0\n'


def test_graph_time_inventory_and_moment_comparison():
    expected = HEADER+ROW
    assert module.compare(expected,expected)['passed']
    assert not module.compare(HEADER,expected)['passed']
    assert not module.compare(expected.replace('\t110\t','\t111\t'),expected)['passed']
    assert not module.compare(expected.replace('0.00001','0.00002'),expected)['passed']
    assert not module.compare(expected.replace('scan','other'),expected)['passed']
    assert module.compare(expected.replace('\t0\n','\t1e-23\n'),expected)['passed']


def test_graph_rejects_duplicate_and_nonfinite_values():
    with pytest.raises(ValueError,match='duplicate'):
        module.compare(HEADER+ROW+ROW,HEADER+ROW)
    with pytest.raises(ValueError,match='nonfinite'):
        module.compare((HEADER+ROW).replace('0.00001','nan'),HEADER+ROW)
