import importlib.util
from pathlib import Path

SPEC=importlib.util.spec_from_file_location('report162_test',Path(__file__).with_name('report.py'))
R=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(R)


def test_ties_incomplete_and_equal_geographic_hypotheses_are_not_arbitrary_successes():
    members=[dict(label=l,dataset='DS16') for l in ('A','B','C')]
    cells=[dict(label=l,hypothesis=h,arm='zero-c',mode='train0',status='qualified',error_km=1.)
           for l in ('A','B','C') for h in R.ARMS]
    prefs=[dict(label=l,arm='zero-c',status=s,selected_hypothesis=h)
           for l,s,h in [('A','selected','zero-c'),('B','tie',None),('C','incomplete',None)]]
    summary=R.summarize(cells,prefs,members)
    a=summary['aggregates'][0]
    assert a['resolved']==1 and a['ties']==1 and a['incomplete']==1
    assert a['evaluable']==1 and a['preference_denominator']==0 and a['geographic_ties']==3
    assert a['selected']['n']==1 and not a['full_coverage']


def test_geographic_errors_are_not_multiplied_by_fit_count():
    members=[dict(label='A',dataset='DS16')]
    cells=[dict(label='A',hypothesis=h,arm=a,mode=m,status='qualified',error_km=e)
           for h,e in [('zero-c',2.),('fitted-c',1.)] for a in R.ARMS for m in ('train0','train1')]
    prefs=[dict(label='A',arm=a,status='selected',selected_hypothesis='zero-c') for a in R.ARMS]
    a=R.summarize(cells,prefs,members)['aggregates'][0]
    assert a['selected']['n']==1 and a['selected']['mean']==2
    assert a['delta']['mean']==1 and a['regression_labels']==['A']
    assert a['preference_correct']==0 and a['preference_denominator']==1
