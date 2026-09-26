"""Independent support, gauge and finite-value audit of actual observations."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent

def audit_rows(rows,window_samples=70000,rate=10000000):
    groups=defaultdict(list)
    for row in rows:
        assert row['valid'] in ('True',True)
        assert np.isfinite(float(row['phase_rad']))
        assert 0<=float(row['weight'])<=1+1e-12
        assert int(row['frame_count'])>=3
        groups[row['group_id']].append(row)
    output=[]
    for group,items in sorted(groups.items()):
        cells=defaultdict(list)
        for row in items:cells[int(row['window_start_sample'])].append(row)
        assert len({float(r['common_rx1_minus_rx0_authority_hz']) for r in items})==1
        ordered=sorted(cells)
        assert all(b-a>=window_samples for a,b in zip(ordered,ordered[1:]))
        train=held=0
        for start,paired in sorted(cells.items()):
            assert len(paired)==2 and len({r['mode'] for r in paired})==2
            assert len({r['alias_group'] for r in paired})==2
            assert len({int(r['device_counter']) for r in paired})==1
            assert len({float(r['time_s']) for r in paired})==1
            assert abs(float(paired[0]['time_s'])-(start+window_samples/2)/rate)<1e-12
            assert abs(float(paired[0]['canonical_cfo_hz'])-float(paired[1]['canonical_cfo_hz']))>=10000
            for row in paired:
                if row['split']=='training':
                    assert start+window_samples<=280000;train+=1
                else:
                    assert row['split']=='evaluation' and start>=280000;held+=1
        output.append(dict(group_id=group,training_rows=train,held_rows=held,synchronized_windows=len(cells)))
    return output

def main():
    path=HERE/'data/observations.csv'
    rows=list(csv.DictReader(path.open()))
    groups=audit_rows(rows)
    payload=dict(status='pass',observation_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),groups=groups,
        total_rows=len(rows),training_rows=sum(g['training_rows'] for g in groups),held_rows=sum(g['held_rows'] for g in groups),
        note='Simultaneous physical midpoint, common authority, disjoint estimator windows and split verified. Per-mode frame samples need not coincide because template epochs differ; phases are transported to midpoint by estimator. Mode independence and geometric identity remain unproven.')
    (HERE/'validation.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2))

if __name__=='__main__':main()
