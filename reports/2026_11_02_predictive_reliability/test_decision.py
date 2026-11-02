import copy
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('reliability_decision',Path(__file__).with_name('decision.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


def inputs():
    plans=[dict(name=f'p{i}',kind='time_group' if i<3 else 'family_receiver',eligible=True) for i in range(5)]
    def density(cost):
        return dict(status='complete',bounded=dict(negative_twice_log_density=cost,
            prior_box=dict(relative_quadrature_error=1e-10),posterior_box=dict(relative_quadrature_error=1e-10)))
    rows=[dict(split=p['name'],arm=a,SD_scale=s,status='complete',numerical_fit_qualified=True,
        train_ids_sha256='train'+p['name'],held_ids_sha256='held'+p['name'],
        scores={key:density(100 if s==1 else 90) for key in ['all','other']})
        for p in plans for a in d.ARMS for s in d.SCALES]
    return plans,rows


def test_positive_scores_do_not_override_missing_receiver_support_or_failed_control():
    plans,rows=inputs();assert d.decide(plans,rows)['verdict']=='SD4_conditionally_favored'
    plans[4]['eligible']=False
    assert d.decide(plans,rows)['verdict']=='inconclusive'
    plans[4]['eligible']=True;rows[0]['numerical_fit_qualified']=False
    assert d.decide(plans,rows)['verdict']=='inconclusive'


def test_cross_arm_contradiction_and_other_family_harm_cannot_be_averaged_away():
    plans,rows=inputs();original=copy.deepcopy(rows)
    rows[-1]['scores']['all']['bounded']['negative_twice_log_density']=101
    assert d.decide(plans,rows)['verdict']=='inconclusive'
    original[1]['scores']['other']['bounded']['negative_twice_log_density']=101
    assert d.decide(plans,original)['verdict']=='inconclusive'


def test_geography_cannot_change_verdict_and_missing_or_duplicate_cells_rejected():
    plans,rows=inputs();before=d.decide(plans,rows)
    for r in rows:r['error_m']=0 if r['SD_scale']==1 else 999999
    assert d.decide(plans,rows)==before
    assert d.decide(plans,rows[:-1])['verdict']=='inconclusive'
    with pytest.raises(ValueError):d.decide(plans,rows+[rows[0]])


def test_native_set_mismatch_and_unresolved_numerical_score_difference_abstain():
    plans,rows=inputs();rows[0]['train_ids_sha256']='different'
    assert d.decide(plans,rows)['verdict']=='inconclusive'
    plans,rows=inputs()
    for r in rows:
        for score in r['scores'].values():score['bounded']['negative_twice_log_density']=100+(1e-8 if r['SD_scale']==1 else 0)
    assert d.decide(plans,rows)['verdict']=='inconclusive'
