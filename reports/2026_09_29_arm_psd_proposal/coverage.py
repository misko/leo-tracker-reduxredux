"""Diagnostic retention of frozen candidate objects, NOT end-to-end recall."""
import argparse
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_28_arm_sparse_proposal/score_cohort.py'
spec=importlib.util.spec_from_file_location('frozen_score',SOURCE)
scoring=importlib.util.module_from_spec(spec);spec.loader.exec_module(scoring)


def paths(dataset):
    if dataset=='DS7':
        return (HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl',
                HERE.parent/'2026_09_28_arm_boundary_fallback/host704-v1/rows.jsonl')
    return (HERE.parent/'2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl',
            HERE.parent/'2026_09_28_arm_ds89_validation/host-boundary-v1/rows.jsonl')


def run(features,output):
    manifest=json.loads((features/'manifest.json').read_text());assert manifest['complete']
    baseline,native_path=paths(manifest['dataset'])
    base=scoring.audit.load_baseline(baseline)
    selected={(r['session_id'],r['visit_index']) for r in manifest['selected']}
    native={}
    for line in native_path.read_text().splitlines():
        r=json.loads(line);key=(r['context']['session_id'],r['context']['visit_index'])
        if key in selected:native[key]={(w['receiver_id'],w['probe_index']):w for w in r['rows']}
    result=defaultdict(lambda:defaultdict(lambda:dict(reference_hits=0,retained_matches=0,windows=0,lanes=0)))
    for line in (features/'rows.jsonl').read_text().splitlines():
        row=json.loads(line);ctx=row['context'];case=(ctx['session_id'],ctx['visit_index'])
        for w in row['windows']:
            key=(w['receiver_id'],w['probe_index']);ref=[c for c in base[case][key]['candidates'] if c['margin']>=.025]
            candidates=native[case][key]['candidates']
            for metric in ('ranking','sqrt_ranking'):
                for k in (3,5,7,9,11):
                    allowed=set(w['proposal'][metric][:k]);kept=[c for c in candidates if c['coarse_bin'] in allowed and c['margin']>=.025]
                    n=scoring.audit.maximum_matches(ref,kept)
                    for rate in ('all',str(ctx['rate_hz'])):
                        v=result[f'{metric}-k{k}'][rate];v['reference_hits']+=len(ref);v['retained_matches']+=n;v['windows']+=1;v['lanes']+=k
    for groups in result.values():
        for v in groups.values():v['fraction']=v['retained_matches']/v['reference_hits'] if v['reference_hits'] else None
    out=dict(scope='Frozen candidate retention only: full masked rerun can change retained candidates',
        dataset=manifest['dataset'],feature_sha256=scoring.audit.sha256(features/'rows.jsonl'),
        baseline_sha256=scoring.audit.sha256(baseline),native_sha256=scoring.audit.sha256(native_path),methods=result)
    output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:{r:round(v['fraction'],4) for r,v in groups.items()} for k,groups in result.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--features',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.features,a.output)
