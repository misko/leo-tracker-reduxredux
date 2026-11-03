"""Frozen original-hit scoring and unpruned-control parity for the prototype."""
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

from features import HERE,sha
from coverage import paths

SOURCE=HERE.parent/'2026_09_28_arm_boundary_fallback/score.py'
spec=importlib.util.spec_from_file_location('boundary_score',SOURCE)
frozen=importlib.util.module_from_spec(spec);spec.loader.exec_module(frozen)


def main():
    result={};combined=defaultdict(lambda:defaultdict(lambda:defaultdict(int)))
    for ds in ('ds7','ds8','ds9'):
        baseline,native_path=paths(ds.upper())
        original={}
        for line in native_path.read_text().splitlines():
            r=json.loads(line);ctx=r['context'];original[(ctx['session_id'],ctx['visit_index'])]={(w['receiver_id'],w['probe_index']):w['candidates'] for w in r['rows']}
        result[ds]={}
        for method in ('full','sqrt3','sqrt5','log9','guard5'):
            folder=HERE/f'host-{ds}-{method}-v2'
            score=frozen.score(folder,baseline)
            records=[json.loads(line) for line in (folder/'rows.jsonl').read_text().splitlines()]
            rows=[w for r in records for w in r['rows']]
            if method=='full':
                for r in records:
                    ctx=r['context'];reference=original[(ctx['session_id'],ctx['visit_index'])]
                    for w in r['rows']:assert w['candidates']==reference[(w['receiver_id'],w['probe_index'])]
            score['mask_counts']=dict(windows=len(rows),full_search_windows=sum(w['coarse_mask']==2047 for w in rows),
                logical_cfo_lanes=sum(w['coarse_mask'].bit_count() for w in rows),simd_groups=sum(w['coarse_lane_groups'] for w in rows))
            (folder/'hit-audit.json').write_text(json.dumps(score,indent=2)+'\n')
            result[ds][method]=dict(totals=score['totals'],by_rate=score['by_rate'],mask_counts=score['mask_counts'])
            for rate,counts in [('all',score['totals']),*score['by_rate'].items()]:
                for key,value in counts.items():
                    if isinstance(value,int):combined[method][rate][key]+=value
    for groups in combined.values():
        for count in groups.values():count['recovery_fraction']=count['recovered_positive_hits']/count['reference_positive_hits']
    output=dict(scope='Actual complete GLRT reruns on 32 metadata-selected dwells per dataset; full-control candidate objects exactly match preceding sealed boundary implementation',
        datasets=result,combined=combined,scorer_sha256=sha(SOURCE))
    (HERE/'native-summary.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({m:{r:(v['recovered_positive_hits'],v['reference_positive_hits'],round(v['recovery_fraction'],4)) for r,v in groups.items()} for m,groups in combined.items()},indent=2))


if __name__=='__main__':main()
