import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('report161_test', Path(__file__).with_name('report.py'))
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_missing_errors_never_zero_filled_or_pair_changed():
    cells = [dict(label='A', dataset='DS16', arm='zero-c', mode='full', status='qualified', error_km=1.),
             dict(label='A', dataset='DS16', arm='zero-c', mode='train0', status='qualified', error_km=2.),
             dict(label='B', dataset='DS16', arm='zero-c', mode='full', status='qualified', error_km=9.),
             dict(label='B', dataset='DS16', arm='zero-c', mode='train0', status='failed')]
    row = next(r for r in REPORT.aggregate(cells) if r['dataset']=='DS16' and r['arm']=='zero-c' and r['mode']=='train0')
    assert row['attempted']==2 and row['qualified']==1
    assert row['paired_delta']['mean']==1 and row['paired_full']['mean']==1
    assert row['errors']['mean']==2 and row['regressions']==1
    assert row['regression_labels']==['A'] and row['maximum_regression_km']==1
    assert row['equal']==0


def test_predictive_comparison_uses_opposite_fold_and_separates_position():
    cells=[]
    for arm, nll, error in [('zero-c', 20., 1.), ('fitted-c', 10., 2.)]:
        cells.append(dict(label='A', dataset='DS16', arm=arm, mode='train0', status='qualified',
            error_km=error, scores={'1':dict(status='complete',nll=nll,observations=10)}))
    row=REPORT.predictive_pairs(cells)[0]
    assert row['delta_nll_per_row']==-1 and row['delta_error_km']==1
