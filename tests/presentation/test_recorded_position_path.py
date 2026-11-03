import copy
import pytest
from leo.presentation.position_path import recorded_position_path

BASE='algo02-causal-family-v1'
NEW='algo07-causal-guarded-reassociation-v1'


def baseline():
    row=dict(endpoint_east_north_km=[6.,-6.],history=[
        dict(fit=dict(parameters=[5.,-5.],history=[dict(parameters=[0.,0.]),dict(parameters=[5.,-5.])]),phase_change_s=.5),
        dict(fit=dict(parameters=[6.,-6.],history=[dict(parameters=[5.,-5.]),dict(parameters=[6.,-6.])]),phase_change_s=.001)])
    return dict(model_version=BASE,arms={a:copy.deepcopy(row) for a in ('c0','fitted_c')})


def test_fallback_uses_real_baseline_history_without_duplicating_it():
    old=baseline();before=copy.deepcopy(old)
    terminal=dict(model_version=NEW,decision='ALGO06_fallback',incumbent=old)
    p=recorded_position_path(terminal,BASE)
    assert len(p['stages'])==1
    rounds=p['stages'][0]['arms']['fitted_c']['rounds']
    assert rounds[0]['points']==[[0.,0.],[5.,-5.]]
    assert rounds[1]['points']==[[5.,-5.],[6.,-6.]]
    assert old==before


def test_reassociation_keeps_distinct_fits_and_labels_endpoint_only_history():
    row=dict(endpoint_east_north_km=[7.,-7.],history=[dict(x=[6.5,-6.5]),dict(x=[7.,-7.])])
    terminal=dict(model_version=NEW,decision='ALGO07_reassociation',incumbent=baseline(),
                  candidate=dict(arms={a:copy.deepcopy(row) for a in ('c0','fitted_c')}))
    p=recorded_position_path(terminal,NEW)
    assert [s['model_version'] for s in p['stages']]==[BASE,NEW]
    rounds=p['stages'][-1]['arms']['fitted_c']['rounds']
    assert rounds[0]['points']==[[6.5,-6.5]]
    assert all(r['detail']=='phase_round_endpoint' for r in rounds)


def test_missing_history_never_fabricates_a_start_or_line():
    old=baseline()
    for row in old['arms'].values():row.pop('history')
    p=recorded_position_path(old,BASE)
    assert not p['stages'][0]['arms']['fitted_c']['history_available']
    assert p['stages'][0]['arms']['fitted_c']['rounds']==[]


def test_history_ending_at_another_point_is_rejected():
    old=baseline();old['arms']['fitted_c']['endpoint_east_north_km']=[0.,0.]
    with pytest.raises(ValueError,match='published endpoint'):recorded_position_path(old,BASE)


def test_compact_accepted_recovery_with_only_latlon_has_no_invented_path():
    model='algo05-causal-gap-conditional-v1'
    terminal=dict(model_version=model,decision='ALGO05_additive',incumbent=baseline(),
        candidate=dict(trial=dict(arms={a:dict(endpoint_latlon=[37.906,-122.545]) for a in ('c0','fitted_c')})))
    p=recorded_position_path(terminal,model)
    row=p['stages'][-1]['arms']['fitted_c']
    assert row['endpoint']==[0.,0.] and not row['history_available'] and not row['rounds']
