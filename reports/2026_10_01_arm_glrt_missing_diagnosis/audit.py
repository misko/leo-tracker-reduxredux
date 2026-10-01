"""Join missing track evidence to original per-dwell detector receipts."""
import csv
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
FULL=REPORTS/'2026_09_30_arm_full_scan_comparison'
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'

def main():
    mapping={r['candidate_id']:r for r in csv.DictReader((BASE/'server-candidate-map.tsv').open(),delimiter='\t')}
    points={}
    for line in (BASE/'server-tracks.tsv').read_text().splitlines():
        f=line.split('\t')
        if f[0]=='POINT':
            m=mapping[f[2]]
            points[(int(f[1]),int(m['visit']),int(m['receiver_id']))]=m
    calls={}
    for p in (FULL/'arm-v2').glob('batch-*.jsonl'):
        begin=int(p.stem.split('-')[1])
        for line in p.read_text().splitlines():
            x=json.loads(line)
            if 'result' in x:calls[begin+x['result']['sequence']]=x['result']
    previous=json.loads((REPORTS/'2026_10_01_arm_rolling_backfill/missing-long/audit.json').read_text())
    records=[]
    for track in previous['rows']:
        for e in track['evidence']:
            if e['available']:continue
            visit,rx,_=map(int,e['source'].split(':'))
            rank=int(points[(track['reference'],visit,rx)]['candidate_rank'])
            server=json.loads((FULL/f'server/visits/visit-{visit:06d}.json').read_text())
            candidate=next(c for c in server['candidates'][str(rx)] if c['rank']==rank)
            arm=next(r for r in calls[visit]['rows'] if r['receiver_id']==rx)
            records.append({'reference':track['reference'],'visit':visit,'receiver':rx,
                'evidence':e,'server_candidate':candidate,'arm_row':arm,
                'all_coarse_rejected':arm['coarse_gate_skipped_count']==arm['retained_peak_count'] and arm['candidate_count']==0})
    (HERE/'missing.json').write_text(json.dumps(records,indent=2)+'\n')
    for ref in [2,30,8,34,47]:
        rows=[r for r in records if r['reference']==ref]
        print(ref,'missing',len(rows),'all coarse rejected',sum(r['all_coarse_rejected'] for r in rows),
            'server integer below .025',sum(r['server_candidate']['margin']<.025 for r in rows))

if __name__=='__main__':main()
