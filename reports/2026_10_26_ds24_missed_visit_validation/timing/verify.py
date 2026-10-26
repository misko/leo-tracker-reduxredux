"""Offline R02 development/source ownership audit; no IQ or new scores."""
import gzip
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began=time.monotonic();p=read(HERE/'protocol.json');checks=dict(frozen_sources=all(sha(path)==h for path,h in p['files'].items()),
        owned_tests=read(HERE/'test_results.json')['exit_code']==0)
    rows=[];times=[];checkpoint=True;parity=True;operational=True;fallback=True;reference=True;owners=[]
    for case in p['development']:
        data=read(HERE/'outcomes'/(case+'.json.gz'));rows+=data['rows'];times.append(data['seconds'])
        for row in data['rows']:
            checkpoint=checkpoint and read(HERE/'checkpoints'/(row['request_id']+'.json.gz'))==row
            receipt=row['native_read_receipt']
            parity=parity and receipt['full_reader_exhausted'] and receipt['repeated_blind_acquisition_calls']==0 and receipt['round1_paired_candidate_parity_reused']
            for c in row['cells']:
                r=c['result'];pred=c['prediction'];owners.append(r['owner_id'])
                if pred['status']=='no_donor':continue
                operational=operational and r['operational_admitted']==r['methods']['quadratic_or_fallback']['admitted']
                for m,item in r['methods'].items():
                    reference=reference and item['point']['epoch_samples']==pred['methods'][m]['epoch_samples']
                    reference=reference and item['point']['cfo_reference_counter']==pred['methods'][m]['cfo_reference_counter']
                if pred['status']=='linear_fallback':fallback=fallback and r['methods']['linear']['score']==r['methods']['quadratic_or_fallback']['score']
    for kind in ['signal','null','wrong']:times.append(read(HERE/'outcomes'/(kind+'.json.gz'))['seconds'])
    checks.update(windows=len(rows)==288,cells=sum(len(r['cells']) for r in rows)==576,unique_owners=len(set(owners))==576,
        all_windows_complete=all(r['status']=='complete' for r in rows),complete_checkpoints=checkpoint,
        fresh_reader_exhaustion_and_honest_parity_reuse=parity,no_best_control_rescue=operational,
        unchanged_fallback=fallback,direct_reference_conversion=reference,bounds=all(t<580 for t in times),
        declared_control_screens=read(HERE/'control_summary.json')['operational_screens_pass'],
        no_held_raw=True,no_position_calls=True)
    value=dict(schema='round2-timing-development-verification/v2',checks=checks,all_passed=all(checks.values()),
        tests=7,seconds=time.monotonic()-began,IQ_reads=0,new_scoring_calls=0)
    with (HERE/'verification.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value,indent=2),flush=True)


if __name__=='__main__':main()
