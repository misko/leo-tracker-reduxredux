import importlib.util
from pathlib import Path
import math
import pytest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('promotion_statistics',HERE/'scan_statistics.py');stats=importlib.util.module_from_spec(spec);spec.loader.exec_module(stats)


def rows(baseline,treatment):
    result=[]
    for i,(b,t) in enumerate(zip(baseline,treatment,strict=True)):
        for arm in stats.ARMS:
            for variant,value in [('baseline',b),('additions_bin_floor',t)]:
                result.append(dict(case=str(i),variant=variant,arm=arm,valid=value is not None,
                    error_m=value,status='complete' if value is not None else 'capped'))
    return result


def test_median_gate_cannot_hide_worse_tail():
    data=rows([100]*12,[70]*10+[150]*2)
    result=stats.compare(data,[str(i) for i in range(12)],'additions_bin_floor')
    assert result['arms']['c0']['gates']['median_at_least_10_percent']
    assert not result['arms']['c0']['gates']['p90_no_increase']
    assert not result['both_c_arms_pass']


def test_failures_stay_visible_and_coverage_blocks_complete_case_win():
    data=rows([100]*12,[50]*11+[None])
    result=stats.compare(data,[str(i) for i in range(12)],'additions_bin_floor')['arms']['c0']
    assert result['complete_cases']['n']==11 and result['complete_cases']['cohort_median_improvement']==.5
    assert result['treatment']['intended_scans']==12 and result['treatment_complete']==11
    assert result['baseline_valid_to_treatment_invalid']==['11'] and not result['gate_pass']


def test_both_arms_must_pass_and_no_eligible_cases_stay_in_denominator():
    data=rows([100]*12,[80]*12)
    for row in data:
        if row['arm']=='fitted_c' and row['variant']!='baseline':row['error_m']=100;row['baseline_equivalent']=True;row['eligible_lane']=False
    result=stats.compare(data,[str(i) for i in range(12)],'additions_bin_floor')
    assert result['arms']['c0']['gate_pass'] and not result['both_c_arms_pass']
    assert len(result['arms']['fitted_c']['scans'])==12


def test_quantiles_and_estimands_are_predeclared():
    assert stats.quantile([0,10,20,30],.9)==27
    assert math.isinf(stats.quantile([0,10,math.inf],.9))
    result=stats.compare(rows([10,100,1000],[9,50,900]),['0','1','2'],'additions_bin_floor')['arms']['c0']
    assert result['cohort_median_improvement']==.5
    assert result['complete_cases']['median_paired_relative_change']==pytest.approx(-.1)


def test_scan_bootstrap_pairs_draws_and_reports_unavailable_replicates():
    data=rows([100]*12,[80]*10+[None,None]);cases=[str(i) for i in range(12)]
    a=stats.bootstrap(data,cases,['additions_bin_floor'],replicates=300)
    b=stats.bootstrap(data,cases,['additions_bin_floor'],replicates=300)
    assert a==b and a['unit']=='paired scan' and a['same_draws_across_variants_and_arms']
    assert a['results']['additions_bin_floor']['c0']['p90_change_m']['finite_fraction']<1


def test_duplicate_or_outside_scan_cannot_enter_analysis():
    data=rows([100],[80])
    with pytest.raises(ValueError):stats.compare(data+data,['0'],'additions_bin_floor')
    with pytest.raises(ValueError):stats.compare(data,['other'],'additions_bin_floor')


def test_exact_ten_percent_boundary_has_no_added_tolerance():
    cases=[str(i) for i in range(12)]
    assert stats.compare(rows([100]*12,[90]*12),cases,'additions_bin_floor')['both_c_arms_pass']
    assert not stats.compare(rows([100]*12,[90.0001]*12),cases,'additions_bin_floor')['both_c_arms_pass']
