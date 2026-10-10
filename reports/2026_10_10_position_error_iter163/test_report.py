import importlib.util
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('report163_test',Path(__file__).with_name('report.py'))
R=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(R)


def test_control_selector_comparison_is_not_the_fitted_source_baseline():
    cells=[dict(label='A',dataset='DS16',hypothesis=h,mode='train0',arm='fitted-c',status='qualified',error_km=e)
           for h,e in [('zero-c',2.),('fitted-c',1.)]]
    choices=dict(candidate=[dict(label='A',arm='fitted-c',status='selected',selected_hypothesis='fitted-c')],
                 control=[dict(label='A',arm='fitted-c',status='selected',selected_hypothesis='zero-c')])
    s=R.summarize(cells,choices,[dict(label='A',dataset='DS16')])
    row=s['rows'][0]
    assert row['delta_vs_control_km']==-1 and row['delta_vs_fitted_hypothesis_km']==0
    a=next(a for a in s['aggregates'] if a['dataset']=='DS16' and a['arm']=='fitted-c')
    assert a['control_paired']['mean']==2 and a['improved_vs_control']==1


def test_unresolved_control_is_not_replaced_with_an_oracle():
    cells=[dict(label='A',dataset='DS16',hypothesis=h,mode='train0',arm='fitted-c',status='qualified',error_km=e)
           for h,e in [('zero-c',2.),('fitted-c',1.)]]
    choices=dict(candidate=[dict(label='A',arm='fitted-c',status='selected',selected_hypothesis='fitted-c')],
                 control=[dict(label='A',arm='fitted-c',status='tie',selected_hypothesis=None)])
    s=R.summarize(cells,choices,[dict(label='A',dataset='DS16')])
    assert s['rows'][0]['delta_vs_control_km'] is None
