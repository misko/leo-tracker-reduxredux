#!/usr/bin/env python3
"""Build Wave 3 with GCC's otherwise-disabled loop unroller."""
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_resampled_omit_fused'

spec=importlib.util.spec_from_file_location('wave3_unroll_builder',BASE/'build.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.ROOT=ROOT
builder.SOURCE=ROOT/'sources'
base_flags=builder.flags

def unroll_flags(target,sanitize=False,budget=2):
    result=base_flags(target,sanitize,budget)
    if not sanitize:
        result.insert(result.index('-Wall'),'-funroll-loops')
    return result

builder.flags=unroll_flags

def build(target):
    record=builder.build(target)
    path=ROOT/record['receipt']
    receipt=json.loads(path.read_text())
    out=path.parent
    for source,stem,proposal in [
        ('test_rank_only.c','test_rank_only',True),
        ('test_boundary_margin_allowed.c','test_boundary_margin_allowed',False),
    ]:
        name=f'{stem}_{target}'
        command=(builder.proposal_test_command(out,target,source,name,target=='sanitizer')
                 if proposal else
                 builder.link_command(out,target,[source],name,target=='sanitizer',0))
        receipt['commands'].append(builder.run(command))
        receipt['binaries'][name]=builder.sha(out/name)
        if target!='arm':
            run=subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,
                                     'stdout':run.stdout,'stderr':run.stderr})
    receipt.update(
        schema='arm-wave3-unroll-build/v1',
        compiler_experiment='-funroll-loops on optimized translation units; disabled for sanitizer',
        semantic_scope='loop transformation only; -fno-fast-math retained; source and FP64 final GLRT unchanged',
        baseline='../2026_09_29_arm_wave3_combined',
    )
    path.write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}

def main():
    records={target:build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({
        'schema':'arm-wave3-unroll-matrix/v1','builds':records},indent=2)+'\n')

if __name__=='__main__':
    main()
