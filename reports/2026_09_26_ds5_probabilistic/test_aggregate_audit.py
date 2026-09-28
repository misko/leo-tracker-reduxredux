import copy
import pytest
from aggregate_audit import aggregate,DEVELOPMENT


def fixture():
    ids=[DEVELOPMENT,'other'];manifest={'captures':[{'session_id':s,'admission_status':'included','sample_rate_hz':5000000} for s in ids]}
    inventory={'captures':[{'session_id':s,'evidence_sha256':'digest','original_location_errors_m':{'reno':200000,'sacramento':10000}} for s in ids]}
    base={'test_observations':10,'negative_log_score_per_test_observation':5.,'uncapped_posterior_expected_weighted_rms_hz':100.,'max_satellite_boundary_mass':0.}
    scans=[]
    for i,s in enumerate(ids):
        sites={name:dict(base) for name in ('reference','reno','sacramento')}
        sites['reno']['negative_log_score_per_test_observation']=6.+i
        sites['sacramento']['negative_log_score_per_test_observation']=4.
        scans.append({'session_id':s,'evidence_sha256':'digest','experiments':[{'noise_scale_hz':100,'mode':'age_satellite','sites':sites}]})
    return {'scans':scans},manifest,inventory


def test_equal_scan_sign_and_development_exclusion():
    out=aggregate(*fixture());rows=out['summaries']
    r=next(r for r in rows if r['scope']=='all42' and r['prior']=='reno')
    assert r['reference_wins']==2 and r['equal_scan_gap']['mean']==-1.5
    r=next(r for r in rows if r['scope']=='excluding_development' and r['prior']=='reno')
    assert r['scan_count']==1 and r['equal_scan_gap']['mean']==-2


def test_missing_and_duplicate_scan_accounting():
    results,m,i=fixture();results['scans'].pop()
    assert aggregate(results,m,i)['missing_sessions']==['other']
    results['scans'].append(copy.deepcopy(results['scans'][0]))
    with pytest.raises(ValueError,match='duplicate'):aggregate(results,m,i)


def test_denominator_and_digest_mismatch_rejected():
    results,m,i=fixture();results['scans'][0]['experiments'][0]['sites']['reno']['test_observations']=9
    with pytest.raises(ValueError,match='denominator'):aggregate(results,m,i)
    results,m,i=fixture();results['scans'][0]['evidence_sha256']='bad'
    with pytest.raises(ValueError,match='digest'):aggregate(results,m,i)
