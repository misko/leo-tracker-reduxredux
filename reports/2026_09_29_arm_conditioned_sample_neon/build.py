#!/usr/bin/env python3
"""Build the Wave4 conditioned four-sample NEON experiment."""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_proposal_preplan'
spec=importlib.util.spec_from_file_location('preplan_builder',BASE/'build.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=ROOT;module.builder.ROOT=ROOT;module.builder.SOURCE=ROOT/'sources'


def main():
    records={}
    for target in ('host','sanitizer','arm'):
        record=module.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text());out=path.parent
        name='test_rank_fast_'+target
        command=module.builder.proposal_test_command(out,target,'test_rank_fast.c',name,target=='sanitizer')
        receipt['commands'].append(module.builder.run(command));receipt['binaries'][name]=module.builder.sha(out/name)
        if target!='arm':
            run=subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(
            schema='arm-conditioned-sample-neon-build/v1',
            baseline='../2026_09_29_arm_wave4_combined',
            conditioned_accumulation='five complex moments in four sample-partial lanes; ARM NEON horizontal reduction per block',
            delta_powers='computed sequentially in registers; no per-sample power cache',
            scientific_scope='conditioned screen moment reduction order only; 41 frequencies, 16 frames, exact rechecks and FP64 final GLRT unchanged')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':record['receipt'],'sha256':module.builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({
        'schema':'arm-conditioned-sample-neon-matrix/v1','builds':records},indent=2)+'\n')


if __name__=='__main__':main()
