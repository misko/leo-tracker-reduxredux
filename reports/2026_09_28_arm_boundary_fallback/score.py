"""Original-hit scoring with explicit candidate-entry versus GLRT-call counts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

SOURCE=Path(__file__).resolve().parent.parent/'2026_09_28_arm_sparse_proposal/score_cohort.py'
spec=importlib.util.spec_from_file_location('frozen_hit_scoring',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def score(folder,baseline):
    result=module.score(folder,baseline)
    manifest=json.loads((folder/'manifest.json').read_text())
    path=folder/('raw.jsonl' if 'raw_sha256' in manifest else 'rows.jsonl')
    records=[json.loads(s) for s in path.read_text().splitlines()]
    windows=[(r['context'],r['native']) for r in records] if path.name=='raw.jsonl' else [(r['context'],w) for r in records for w in r['rows']]
    for counts in [result['totals'],*result['by_rate'].values()]:
        counts['candidate_entries']=counts.pop('actual_candidate_glrts')
        counts['conditioned_fallbacks']=0
    for ctx,w in windows:
        n=sum(bool(c['conditioned_fallback']) for c in w['candidates'])
        assert n==w['conditioned_fallback_count']
        result['totals']['conditioned_fallbacks']+=n
        result['by_rate'][str(ctx['rate_hz'])]['conditioned_fallbacks']+=n
    for counts in [result['totals'],*result['by_rate'].values()]:
        counts['actual_glrt_kernel_calls']=counts['candidate_entries']+counts['conditioned_fallbacks']
    result['schema']='boundary-fallback-hit-and-work-audit/v1'
    result['frozen_scorer_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=Path('reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    x=score(a.cohort,a.baseline);a.output.write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x['totals'],indent=2))
