"""Explain direct-GLRT changes at identical coarse proposals, not hit matching."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def load(path):
    rows={}
    for line in path.read_text().splitlines():
        row=json.loads(line);c=row['context'];key=(c['session_id'],c['visit_index'])
        assert key not in rows and row['returncode']==0
        rows[key]=row
    return rows


def diagnose(baseline,candidate):
    ref=load(baseline);got=load(candidate);totals=defaultdict(int);by_rate={}
    for case,row in got.items():
        old=ref[case];assert old['context']['sha256']==row['context']['sha256']
        windows={(w['receiver_id'],w['probe_index']):w for w in old['rows']}
        counts=by_rate.setdefault(str(row['context']['rate_hz']),defaultdict(int))
        for w in row['rows']:
            key=(w['receiver_id'],w['probe_index'])
            a={(c['coarse_epoch'],c['coarse_bin']):c for c in windows[key]['candidates']}
            b={(c['coarse_epoch'],c['coarse_bin']):c for c in w['candidates']}
            assert a.keys()==b.keys() and len(a)==len(b)==8
            for proposal,expected in a.items():
                actual=b[proposal];assert actual['epoch']==expected['epoch']
                facts=dict(candidate_pairs=1,baseline_positive=expected['margin']>=.025)
                if expected['margin']>=.025:
                    positive=actual['margin']>=.025
                    delta=abs(actual['tracking_cfo_hz']-expected['tracking_cfo_hz'])
                    facts['became_negative']=not positive
                    facts['positive_but_cfo_shift_over_8khz']=positive and delta>8000
                    facts['positive_cfo_shift_near_symbol_alias']=positive and abs(delta-1/4.4e-6)<=8000
                    facts['same_proposal_positive_within_cfo_gate']=positive and delta<=8000
                for k,v in facts.items():totals[k]+=v;counts[k]+=v
    return dict(scope='Same coarse proposal diagnosis; not one-to-one scientific hit-recovery metric',
        totals=dict(totals),by_rate={r:dict(c) for r,c in by_rate.items()},
        baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();x=diagnose(a.baseline,a.candidate);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['totals'],indent=2))
