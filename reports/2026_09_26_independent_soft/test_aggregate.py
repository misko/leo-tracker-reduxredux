import pytest
from aggregate import summarize


def test_accounting_direction_and_large_error_scope():
    def fit(nll):return {'composite_nll_per_test_block':nll,'mean_null_probability':.1,
        'ambiguous_tracks_maxprob_below_0_8':0,'tracks':[{'track_id':'t','test_blocks':2}]}
    results={s:{'100.0':{'m':fit(v)},'200.0':{'m':fit(v)}} for s,v in
        [('reference',1.),('sacramento',2.),('reno',.5)]}
    scan={'session_id':'s','evidence_sha256':'x','track_count':1,'results':results}
    inv={'captures':[{'session_id':'s','evidence_sha256':'x','track_count':1,'sample_rate_hz':1,
        'original_location_errors_m':{'sacramento':1000,'reno':200000}}]}
    out=summarize([scan],inv)
    sac=next(r for r in out['summaries'] if r['scope']=='all42' and r['site']=='sacramento' and r['noise_hz']==100)
    reno=next(r for r in out['summaries'] if r['scope']=='all42' and r['site']=='reno' and r['noise_hz']==100)
    assert sac['reference_wins']==1 and sac['mean_gap']==-1
    assert reno['reference_wins']==0 and reno['mean_gap']==.5
    large=[r for r in out['summaries'] if r['scope'].endswith('_error_ge100km')]
    assert {(r['scope'],r['site']) for r in large}=={('reno_error_ge100km','reno')}
    with pytest.raises(ValueError,match='duplicate'):summarize([scan,scan],inv)
