import copy
import pytest
from aggregate import summarize


def fixture():
    ids=['scan-fw-dc1153010e57ac76','fresh'];scans=[];inventory={'captures':[]}
    for i,sid in enumerate(ids):
        inventory['captures'].append({'session_id':sid,'evidence_sha256':'x','sample_rate_hz':5000000,
            'original_location_errors_m':{'sacramento':1000,'reno':200000}})
        experiments=[]
        for mode,value in [('old_frozen',6.),('empirical_frozen',7.)]:
            ref={'negative_log_score_per_test_observation':5.,'test_observations':10,
                'uncapped_posterior_expected_weighted_rms_hz':100.,'max_satellite_boundary_mass':0.}
            prior=dict(ref,negative_log_score_per_test_observation=value+i)
            experiments.append({'mode':mode,'sites':{'reference':ref,'sacramento':prior,'reno':prior}})
        scans.append({'session_id':sid,'capture_start_utc':str(i),'evidence_sha256':'x','experiments':experiments})
    return scans,inventory


def test_sign_pairing_and_two_development_exclusion():
    out=summarize(*fixture())
    row=next(r for r in out['summaries'] if r['scope']=='excluding_two_development' and r['mode']=='empirical_frozen' and r['prior']=='reno')
    assert row['scans']==row['reference_wins']==1 and row['mean_gap']==-3
    pair=next(r for r in out['paired_comparisons'] if r['scope']=='all42' and r['prior']=='reno')
    assert pair['mean_gap_change']==-1


def test_accounting_and_digest_guards():
    scans,inv=fixture();assert summarize(scans[:1],inv)['missing_sessions']==['fresh']
    with pytest.raises(ValueError,match='duplicate'):summarize(scans+scans[:1],inv)
    scans[0]['evidence_sha256']='bad'
    with pytest.raises(ValueError,match='evidence'):summarize(scans,inv)
