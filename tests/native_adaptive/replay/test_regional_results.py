import copy
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('regional_result',Path(__file__).resolve().parents[3]/'tools/compare_regional_results.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture():
    return {'schema':'test','evaluated_points':400,'budget_points':400,'deferred_cells':8,
            'complete':False,'stop_reason':'point-budget-reached',
            'selected':{'east_km':0,'north_km':0,'score_hz':100.},
            'evaluations':[[i,0,100.] for i in range(400)]}


def test_exact_and_explicit_tolerance_do_not_hide_coordinate_changes():
    ref=fixture();actual=copy.deepcopy(ref)
    assert module.compare(actual,ref,0)['passed']
    actual['evaluations'][10][2]+=1e-10
    assert not module.compare(actual,ref,0)['passed']
    assert module.compare(actual,ref,1e-9)['passed']
    actual['evaluations'][10][0]+=1
    assert not module.compare(actual,ref,1e-9)['passed']


def test_counts_scores_selection_and_status_are_all_checked():
    ref=fixture()
    for key,value in [('selected',{'east_km':1,'north_km':0,'score_hz':100.}),('complete',True),('deferred_cells',9)]:
        actual=copy.deepcopy(ref);actual[key]=value
        assert not module.compare(actual,ref,1e-9)['passed']
    actual=copy.deepcopy(ref);actual['evaluations'][0][2]=float('nan')
    with pytest.raises(ValueError):module.compare(actual,ref,1e-9)
    actual=copy.deepcopy(ref);actual['evaluations'].pop()
    with pytest.raises(ValueError):module.compare(actual,ref,1e-9)
    with pytest.raises(ValueError):module.compare(ref,ref,1)
