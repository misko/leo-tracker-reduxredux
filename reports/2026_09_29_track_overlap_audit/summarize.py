import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    rows=[]
    for ds in ('DS7','DS8','DS9'):
        assert json.loads((HERE/f'{ds}.receipt.json').read_text())['exit_code']==0
        scans=json.loads((HERE/f'{ds}.json').read_text())['scans']
        rows.append(dict(dataset=ds,scans=len(scans),tracks=sum(s['tracks'] for s in scans),observations=sum(s['observations'] for s in scans),scans_with_reuse=sum(s['cross_track_reused_keys']>0 for s in scans),reused_keys=sum(s['cross_track_reused_keys'] for s in scans),excess_copies=sum(s['excess_cross_track_copies'] for s in scans),train_held_reuse=sum(s['train_held_reused_keys'] for s in scans),within_track_repeated_timestamps=sum(s['repeated_within_track_timestamps'] for s in scans),eligible_history_pairs=sum(len(s['pairs']) for s in scans),similar_history_pairs=sum(p['similar_history'] for s in scans for p in s['pairs']),training_reused_keys=sum(any(u[1] for u in d['uses']) for s in scans for d in s['duplicates']),held_reused_keys=sum(any(not u[1] for u in d['uses']) for s in scans for d in s['duplicates'])))
    totals={k:sum(r[k] for r in rows) for k in rows[0] if k!='dataset'}
    totals['excess_observation_fraction']=totals['excess_copies']/totals['observations']
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows,totals=totals),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(dict(rows=rows,totals=totals),indent=2))


if __name__=='__main__':
    main()
