import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('search_progress',
    Path(__file__).resolve().parents[3]/'tools/evaluate_search_progress.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_partial_is_not_completion_and_mismatch_is_visible():
    reference={'evaluations':[[0,0,100],[1,0,90]]}
    point={'kind':'search_point','sequence':0,'east_km':0,'north_km':0,'score_hz':100,'wall_s':2}
    result=module.evaluate([point],reference,124)
    assert result['completed_prefix_exact'] and not result['full_search_qualified']
    second={**point,'sequence':1,'east_km':1,'score_hz':90}
    assert module.evaluate([point,second],reference,0,reference)['full_search_qualified']
    assert not module.evaluate([point,second],reference,0,None)['full_search_qualified']
    assert module.evaluate([{**point,'score_hz':101}],reference,124)['mismatched_points']==[0]
    assert module.evaluate([{**point,'score_hz':101}],reference,124)['maximum_score_delta_hz']==1
    with pytest.raises(ValueError,match='sequence'):
        module.evaluate([second],reference,124)
