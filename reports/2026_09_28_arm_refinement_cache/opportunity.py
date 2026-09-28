"""Measure repeated refinement keys without dropping candidate hypotheses."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def window_counts(candidates):
    epochs=set();fine=set();final=set()
    result=dict(windows=1,candidates=len(candidates),repeated_epoch=0,
                repeated_epoch_fine_cfo=0,repeated_epoch_final_cfo=0,
                positive_candidates=0,repeated_positive_final_cfo=0)
    for c in candidates:
        epoch=c['refined_epoch'];fine_key=(epoch,c['fine_cfo_hz'])
        final_key=(epoch,c['acquired_cfo_hz'])
        result['repeated_epoch']+=epoch in epochs
        result['repeated_epoch_fine_cfo']+=fine_key in fine
        result['repeated_epoch_final_cfo']+=final_key in final
        result['positive_candidates']+=c['margin']>=.025
        result['repeated_positive_final_cfo']+=c['margin']>=.025 and final_key in final
        epochs.add(epoch);fine.add(fine_key);final.add(final_key)
    return result


def summarize(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['complete']
    totals=defaultdict(int);rates={};dwells=0;seen=set()
    for line in (folder/'rows.jsonl').read_text().splitlines():
        row=json.loads(line);c=row['context'];case=(c['session_id'],c['visit_index'])
        assert case not in seen and row['returncode']==0
        seen.add(case);dwells+=1
        rate=rates.setdefault(str(c['rate_hz']),defaultdict(int))
        keys={(w['receiver_id'],w['probe_index']) for w in row['rows']}
        assert keys=={(r,i) for r in range(2) for i in range(11)} and len(row['rows'])==22
        for w in row['rows']:
            for key,value in window_counts(w['candidates']).items():
                totals[key]+=value;rate[key]+=value
    assert dwells==manifest['processed_dwells']
    return dict(scope='Repeated exact keys within each window; candidate multiplicity remains unchanged',
        caveat='Same epoch and fine CFO does not alone prove identical conditioned grid; runtime cache must key exact grid bounds/count.',
        dwells=dwells,totals=dict(totals),by_rate={r:dict(v) for r,v in rates.items()},
        source_rows_sha256=hashlib.sha256((folder/'rows.jsonl').read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();x=summarize(a.cohort);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['totals'],indent=2))
