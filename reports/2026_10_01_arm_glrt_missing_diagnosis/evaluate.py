"""Verify physical control reproducibility and classify gate-ablation recovery."""
import json
from pathlib import Path
from statistics import median
import csv

HERE=Path(__file__).resolve().parent
FULL=HERE.parent/'2026_09_30_arm_full_scan_comparison'

def circular(x,p):return abs((x+p/2)%p-p/2)

def main():
    original={}
    for p in (FULL/'arm-v2').glob('batch-*.jsonl'):
        begin=int(p.stem.split('-')[1])
        for line in p.read_text().splitlines():
            x=json.loads(line)
            if 'result' in x:original[begin+x['result']['sequence']]=x['result']
    calls={label:{} for label in ['ordinary','ungated']}
    for p in (HERE/'physical').glob('visits-*.json'):
        visits=json.loads(p.read_text());suffix=p.stem.split('-')[1]
        for label in calls:
            for line in (p.parent/f'{label}-{suffix}.jsonl').read_text().splitlines():
                x=json.loads(line)
                if 'result' in x:calls[label][visits[x['result']['sequence']]]=x['result']
    for v,call in calls['ordinary'].items():
        for old,new in zip(original[v]['rows'],call['rows']):
            assert {k:x for k,x in old.items() if k!='timings_ms'}=={k:x for k,x in new.items() if k!='timings_ms'},v
    inventory={x['visit']:x for x in json.loads((FULL/'arm-v2/inventory.json').read_text())}
    records=json.loads((HERE/'missing.json').read_text())
    for r in records:
        source=inventory[r['visit']]['event'];scale=11.2e9/(source['target']['rf_center_hz']-source['actual_if_offset_hz'])
        server_source=json.loads((FULL/f'server/visits/visit-{r["visit"]:06d}.json').read_text())['source']
        assert server_source['raw_sha256']==inventory[r['visit']]['raw_sha256']
        assert server_source['event']==source
        row=next(x for x in calls['ungated'][r['visit']]['rows'] if x['receiver_id']==r['receiver'])
        expected=r['server_candidate']['fractional_tracking_cfo_hz'];period=1/4.4e-6
        good=[c for c in row['candidates'] if c['margin']>=.025 and circular(c['tracking_cfo_hz']-expected,period)*scale<=2500]
        r['ungated_recovered']=bool(good)
        r['ungated_matching_candidates']=good
        r['ungated_row']=row
        r['nearest_ungated_cfo_error_hz']=min((circular(c['tracking_cfo_hz']-expected,period)*scale for c in row['candidates']),default=None)
        r['nearest_ungated_epoch_distance_samples']=min((circular(c['epoch']-r['server_candidate']['epoch'],3333)
                                                       for c in row['candidates']),default=None)
        if good:
            assert all(c['coarse_score']<.314 for c in good), 'Unexpected recovery above original cutoff'
    summary=[]
    for ref in [2,30,8,34,47]:
        rs=[r for r in records if r['reference']==ref]
        summary.append({'reference':ref,'missing':len(rs),'all_coarse_rejected':sum(r['all_coarse_rejected'] for r in rs),
            'ungated_recovered':sum(r['ungated_recovered'] for r in rs),
            'remaining_visits':[r['visit'] for r in rs if not r['ungated_recovered']]})
    result={'summary':summary,'all_control_rows_identical_to_original':True,'physical_dwells':len(calls['ordinary']),
        'missing_source_count':len(records),'recovered_sources':sum(r['ungated_recovered'] for r in records),
        'server_integer_margin_range':[min(r['server_candidate']['margin'] for r in records),max(r['server_candidate']['margin'] for r in records)],
        'recovered_coarse_score_range':[min(c['coarse_score'] for r in records for c in r['ungated_matching_candidates']),
                                        max(c['coarse_score'] for r in records for c in r['ungated_matching_candidates'])],
        'remaining_epoch_farther_than_2_samples':sum(not r['ungated_recovered'] and r['nearest_ungated_epoch_distance_samples']>2 for r in records),
        'timings_selected_missing_dwells_only':{k:{'median_ms':median(x['call_wall_ms'] for x in v.values()),
            'max_ms':max(x['call_wall_ms'] for x in v.values()),
            'calls_at_least_120ms':sum(x['call_wall_ms']>=120 for x in v.values())} for k,v in calls.items()},'records':records}
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))

if __name__=='__main__':main()
