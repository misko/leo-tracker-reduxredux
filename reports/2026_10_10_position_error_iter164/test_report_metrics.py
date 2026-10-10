"""Pure already-evaluated synthetic rows, no recording/model/reference calls."""
import copy
import importlib.util
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('metrics164_test',Path(__file__).with_name('report_metrics.py'))
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def fixture():
    membership=[];rows=[]
    for dataset,count in M.COUNTS.items():
        for i in range(count):
            label=f'{dataset}-{i:03}';membership.append(dict(label=label,dataset=dataset))
            arms={}
            for arm in M.ARMS:
                arms[arm]={branch:dict(status='selected',qualified=True,
                    error_km=(2. if arm=='zero-c' else 1.)+(0.25 if branch=='zero' else 0.),
                    frequency=dict(objective=-10.,posterior_rms_hz=100.,signal_windows=20.)) for branch in M.BRANCHES}
            rows.append(dict(label=label,dataset=dataset,arms=arms))
    return membership,rows


def test_full193_metrics_and_separate_within_branch_c_effect():
    members,rows=fixture();result=M.aggregate(members,rows);allrows=result['datasets']['all193']
    d=allrows['discovery']['fitted-c']
    assert d['paired']==193 and d['regressions']==193
    assert d['full_metrics']['left']['mean']==1. and d['full_metrics']['right']['median']==1.25
    assert allrows['c_effect']['native']['full_metrics']['delta']['mean']==-1.
    assert allrows['c_effect']['native']['improvements']==193
    assert allrows['frequency']['native']['fitted-c']['objective']['full_metrics']['mean']==-10.
    assert result['datasets']['DS16']['membership']==63


def test_missing_row_withholds_full_metrics_without_zero_fill():
    members,rows=fixture();missing=rows.pop(0)['label'];result=M.aggregate(members,rows)
    d=result['datasets']['all193']['discovery']['fitted-c']
    assert d['full_metrics'] is None and d['paired']==192 and d['missing_labels']==[missing]
    assert d['available_pair_metrics']['left']['mean']==1.
    assert result['datasets']['DS17']['discovery']['fitted-c']['full_metrics'] is not None
    assert result['coverage'][0]['row_present'] is False


def test_missing_arm_preserves_other_comparisons_and_failure_reason():
    members,rows=fixture();rows[0]['arms']['fitted-c']['zero']=dict(status='no-selected-endpoint',reason='calibration failed')
    rows[0]['failure_reasons']={'zero':'calibration failed'}
    result=M.aggregate(members,rows);d=result['datasets']['all193']
    assert d['discovery']['fitted-c']['full_metrics'] is None
    assert d['discovery']['zero-c']['full_metrics'] is not None
    assert d['c_effect']['zero']['full_metrics'] is None and d['c_effect']['native']['complete']
    assert result['coverage'][0]['failure_reasons']['zero']=='calibration failed'


def test_recompute_delta_do_not_trust_inherited_alias_and_preserve_ties():
    members,rows=fixture()
    rows[0]['arms']['fitted-c']['zero']['error_km']=1.+1e-10
    rows[0]['arms']['fitted-c']['delta_km']=1000.
    result=M.aggregate(members,rows)['datasets']['all193']['discovery']['fitted-c']
    assert result['equal']==1 and result['regressions']==192 and not result['regressions_over_1km']


def test_statistics_linear_quantile_and_empty():
    assert M.statistics([]) is None
    assert M.statistics([0.,10.])==dict(n=2,mean=5.,median=5.,p95=9.5,worst=10.)


@pytest.mark.parametrize('fault',['duplicate','foreign','dataset','nan','negative','unqualified','fixed-alias','membership'])
def test_invalid_evaluation_never_silently_dropped(fault):
    members,rows=fixture()
    if fault=='duplicate':rows.append(copy.deepcopy(rows[0]))
    if fault=='foreign':rows[0]['label']='foreign'
    if fault=='dataset':rows[0]['dataset']='DS17'
    if fault=='nan':rows[0]['arms']['zero-c']['native']['error_km']=float('nan')
    if fault=='negative':rows[0]['arms']['zero-c']['native']['error_km']=-1.
    if fault=='unqualified':rows[0]['arms']['zero-c']['native']['qualified']=False
    if fault=='fixed-alias':rows[0]['arms']['zero-c']['fixed']=rows[0]['arms']['zero-c'].pop('zero')
    if fault=='membership':members.pop()
    with pytest.raises(ValueError):M.aggregate(members,rows)


def test_frequency_missingness_independent_of_position_coverage():
    members,rows=fixture();rows[0]['arms']['zero-c']['native']['frequency']['posterior_rms_hz']=None
    result=M.aggregate(members,rows)['datasets']['all193']
    assert result['discovery']['zero-c']['complete']
    rms=result['frequency']['native']['zero-c']['posterior_rms_hz']
    assert rms['full_metrics'] is None and rms['available']==192
