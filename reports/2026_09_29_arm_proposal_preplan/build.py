#!/usr/bin/env python3
"""Build Wave 3 with immutable proposal geometry preplans."""
import importlib.util,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_resampled_omit_fused'
spec=importlib.util.spec_from_file_location('proposal_preplan_builder',BASE/'build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
builder.ROOT=ROOT;builder.SOURCE=ROOT/'sources'

def build(target):
    record=builder.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text());out=path.parent
    extras=[('test_rank_only.c','test_rank_only',True),
            ('test_boundary_margin_allowed.c','test_boundary_margin_allowed',False),
            ('test_preplan.c','test_preplan',True)]
    for source,stem,proposal in extras:
        name=f'{stem}_{target}'
        command=(builder.proposal_test_command(out,target,source,name,target=='sanitizer') if proposal
                 else builder.link_command(out,target,[source],name,target=='sanitizer',0))
        receipt['commands'].append(builder.run(command));receipt['binaries'][name]=builder.sha(out/name)
        if target!='arm':
            run=subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
    receipt.update(schema='arm-proposal-preplan-build/v1',
        proposal_preplan='resample source/fraction, frame offsets, per-lag valid lengths and support counts',
        arithmetic='original float interpolation expression and support division retained exactly',
        baseline='../2026_09_29_arm_wave3_combined')
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}

def main():
    records={target:build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-proposal-preplan-matrix/v1','builds':records},indent=2)+'\n')

if __name__=='__main__':main()
