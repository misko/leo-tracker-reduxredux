import pytest
from aggregate_ds5_constant import summarize


def test_summary_direction_and_accounting():
    sites={s:{'rms_hz':v,'capped800_rms_hz':v} for s,v in [('reference',10.),('reno',20.),('sacramento',5.)]}
    scans=[{'session_id':'a','evidence_sha256':'x','scores':{'zero':sites}}]
    inventory={'captures':[{'session_id':'a','evidence_sha256':'x','original_location_errors_m':{'reno':110000,'sacramento':1000}}]}
    result=summarize(scans,inventory)
    assert result['missing']==[]
    reno=next(r for r in result['summaries'] if r['scope']=='all' and r['site']=='reno' and r['metric']=='rms_hz')
    assert reno['reference_wins']==1 and reno['mean_gap_hz']==-10
    with pytest.raises(ValueError):summarize(scans+scans,inventory)
    scans[0]['evidence_sha256']='bad'
    with pytest.raises(ValueError):summarize(scans,inventory)
