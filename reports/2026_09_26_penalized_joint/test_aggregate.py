import pytest
from aggregate import summarize


def test_direction_and_accounting():
    def fit(nll,changes=0):return {'negative_log_score_per_test_observation':nll,'test_observations':2,'identity_changes_from_original':changes}
    scan={'session_id':'s','evidence_sha256':'x','track_count':1,'experiments':[{'change_penalty_nats':2.,
        'sites':{'reference':fit(1),'sacramento':fit(2,1),'reno':fit(.5,1)}}]}
    inv={'captures':[{'session_id':'s','evidence_sha256':'x','track_count':1,'sample_rate_hz':1,
        'original_location_errors_m':{'sacramento':1000,'reno':200000}}]}
    out=summarize([scan],inv)
    sac=next(r for r in out['summaries'] if r['scope']=='all42' and r['site']=='sacramento')
    reno=next(r for r in out['summaries'] if r['scope']=='all42' and r['site']=='reno')
    assert sac['reference_wins']==1 and sac['mean_gap']==-1
    assert reno['reference_wins']==0 and reno['mean_gap']==.5
    large=[r for r in out['summaries'] if r['scope'].endswith('_error_ge100km')]
    assert [(r['scope'],r['site']) for r in large]==[('reno_error_ge100km','reno')]
    with pytest.raises(ValueError):summarize([scan,scan],inv)
