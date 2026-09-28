import copy
import pytest
from run_full import verify
from summarize_full import summarize


def fixture():
    sites={}
    for site,score in [('reference',2.),('sacramento',1.),('reno',3.)]:
        sites[site]={}
        for noise in ('100.0','200.0'):
            fit={'composite_nll_per_test_block':score,'mean_null_probability':0.,
                'tracks':[{'track_id':'t','test_blocks':2,'predictive_log_score':-2*score,'probabilities':{'sat':1.}}]}
            sites[site][noise]={m:copy.deepcopy(fit) for m in ('joint','joint_no_clock','frozen_no_clock')}
            sites[site][noise].update(chain_nll=[score,score],max_chain_assignment_total_variation=0.)
    scan={'session_id':'s','capture_start_utc':'2026-09-26T09:00:00Z','evidence_sha256':'x','track_count':1,
        'max_prior_mass_outside_support':.01,'results':sites}
    inventory={'captures':[{'session_id':'s','evidence_sha256':'x','track_count':1,'sample_rate_hz':2500000,
        'original_location_errors_m':{'reno':150000,'sacramento':1000}}]}
    return scan,inventory


def test_summary_direction_and_guards():
    scan,inventory=fixture();out=summarize([scan],inventory,set())
    r=next(r for r in out['summaries'] if r['scope']=='all42' and r['site']=='reno' and r['noise_hz']==100 and r['model']=='joint')
    assert r['reference_wins']==1 and r['mean_gap']==-1 and not out['missing']
    assert len([r for r in out['summaries'] if r['scope']=='new35'])==12
    with pytest.raises(ValueError):summarize([scan,scan],inventory,set())
    scan['evidence_sha256']='bad'
    with pytest.raises(ValueError):summarize([scan],inventory,set())


def test_compatibility_guards():
    baseline={'source_sha256':'a','core_sha256':'b','calibration_sha256':'c'}
    verify(baseline,baseline)
    with pytest.raises(ValueError):verify(dict(baseline,core_sha256='different'),baseline)


def test_invalid_scores_are_not_silently_aggregated():
    scan,inventory=fixture()
    scan['results']['reno']['100.0']['joint']['composite_nll_per_test_block']=float('nan')
    with pytest.raises(ValueError):summarize([scan],inventory,set())
