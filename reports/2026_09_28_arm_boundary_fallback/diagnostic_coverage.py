"""Retrospective threshold selection evidence; not a recovery benchmark."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def analyze(full,direct):
    references={}
    for line in full.read_text().splitlines():
        row=json.loads(line)
        references[row['context']['ordinal']]={(w['receiver_id'],w['probe_index'],c['coarse_epoch'],c['coarse_bin']):c
            for w in row['rows'] for c in w['candidates']}
    counts=Counter();gates={str(g):Counter() for g in (500,1000,2000,4000)}
    for line in direct.read_text().splitlines():
        row=json.loads(line)
        for w in row['rows']:
            for c in w['candidates']:
                b=references[row['context']['ordinal']][w['receiver_id'],w['probe_index'],c['coarse_epoch'],c['coarse_bin']]
                positive=b['margin']>=.025
                mismatch=positive and abs(c['tracking_cfo_hz']-b['tracking_cfo_hz'])>8000
                residual=c['tracking_cfo_hz']-c['acquired_cfo_hz']
                distance=abs(abs(residual)-1/(2*4.4e-6))
                counts['candidates']+=1;counts['baseline_positive']+=positive
                counts['positive_frequency_mismatch']+=mismatch
                for gate,v in gates.items():
                    if distance<=int(gate):
                        v['flagged_candidates']+=1;v['flagged_positive_frequency_mismatches']+=mismatch
    return dict(scope='Same-proposal retrospective boundary coverage; threshold tuned on entire704cohort',
                totals=dict(counts),gates_hz={k:dict(v) for k,v in gates.items()},
                full_sha256=hashlib.sha256(full.read_bytes()).hexdigest(),direct_sha256=hashlib.sha256(direct.read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('full','direct','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();x=analyze(a.full,a.direct);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['gates_hz'],indent=2))
