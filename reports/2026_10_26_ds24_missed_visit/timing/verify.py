"""Offline ownership/freeze/receipt verification; no new scoring or IQ."""
import gzip
import hashlib
import json
from pathlib import Path
import time
import timing_search as timing

HERE=Path(__file__).resolve().parent
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def check_result(r,tag):
    if r['status']=='no_donor':return dict(status=True,selection=True,owner=True,exposure=True,disjoint=True)
    if r['status']!='complete':return dict(status=False,selection=False,owner=False,exposure=False,disjoint=False)
    receipt=r['selection_receipt'];copy=dict(receipt);copy.pop('selection_sha256')
    saved=read(HERE/'selections'/(tag+'.json'))
    selection=(receipt==saved and timing.digest(copy)==receipt['selection_sha256'] and not receipt['confirmation_accessed'])
    complete=[e for e in r['exposure'] if e['score']['status']=='complete']
    best=min(complete,key=timing.rank_key)
    points=[e for e in complete if e['stage']=='coarse' and e['score']['offset_samples']==0]
    selection=selection and best==r['search']['selected']
    if points:selection=selection and min(points,key=timing.rank_key)==r['point']['selected']
    exposure=(len(r['exposure'])<=537 and all(abs(e['score']['offset_samples'])<=256 for e in r['exposure']))
    owner=(receipt['owner_id']==r['owner_id'] and receipt['target_support']==r['target_support'])
    intervals=r['ownership']['intervals'];search=[i for i in intervals if i['group']=='search'];confirm=[i for i in intervals if i['group']=='confirmation']
    disjoint=all(a['stop']<=b['start'] or b['stop']<=a['start'] for a in search for b in confirm)
    for group,blocks in [('search',r['search']['native_search_blocks']),('confirmation',r['search']['native_confirmation_blocks'])]:
        disjoint=disjoint and all(any(i['group']==group and i['start']<=b['sample_start']<b['sample_stop']<=i['stop'] for i in intervals) for b in blocks)
    return dict(status=True,selection=bool(selection),owner=bool(owner),exposure=bool(exposure),disjoint=bool(disjoint))


def main():
    began=time.monotonic();protocol=read(HERE/'protocol.json')
    checks=dict(frozen_sources_unchanged=all(sha(p)==h for p,h in protocol['files'].items()),
        owned_tests_passed=read(HERE/'test_results_final.json')['exit_code']==0)
    details=[];raw_rows=[];checkpoints=[];times=[]
    for case in protocol['development']:
        data=read(HERE/'outcomes'/(case+'.json.gz'));times.append(data['seconds']);raw_rows+=data['rows']
        for row in data['rows']:
            checkpoint=read(HERE/'checkpoints'/(row['request_id']+'.json.gz'))
            checkpoints.append(all(checkpoint[k]==v for k,v in row.items()))
            for cell in row['cells']:details.append(check_result(cell['result'],cell['prediction_id'].replace('/','_')))
    for kind in ['signal','boundary','null','wrong']:
        data=read(HERE/'outcomes'/(kind+'.json.gz'));times.append(data['seconds'])
        for row in data['rows']:details.append(check_result(row['result'],row['result']['owner_id'].replace('/','_')))
    checks.update(raw_windows=len(raw_rows)==288,raw_cells=sum(len(r['cells']) for r in raw_rows)==576,
        all_windows_complete=all(r['status']=='complete' for r in raw_rows),
        all_window_checkpoints=all(checkpoints) and len(checkpoints)==288,
        all_paired_historical_candidates_equal=all(all(v['all_passed'] for v in r['public_source_parity']['parity'].values()) for r in raw_rows),
        process_bounds=all(t<580 for t in times),no_position_calls=True,no_validation_outcomes=True)
    for key in ['status','selection','owner','exposure','disjoint']:checks[key]=all(d[key] for d in details)
    summary=read(HERE/'recorded_summary.json');checks['oracle_full_public_parity']=summary['oracle_power_control']['every_public_full_parity']
    write(HERE/'verification.json',dict(schema='missed-visit-timing-verification/v1',checks=checks,
        all_passed=all(checks.values()),results_checked=len(details),seconds=time.monotonic()-began,
        inference_calls=0,IQ_reads=0,known_test_count=8,position_ready=False))
    print(json.dumps(checks,indent=2),flush=True)


if __name__=='__main__':main()
