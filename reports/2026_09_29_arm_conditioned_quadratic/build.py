#!/usr/bin/env python3
"""Build Wave4 quadratic conditioned screens with 32/64-sample blocks."""
import importlib.util,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_proposal_preplan'
spec=importlib.util.spec_from_file_location('preplan_builder',BASE/'build.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=ROOT;module.builder.ROOT=ROOT;module.builder.SOURCE=ROOT/'sources'


def with_block(command,block):
    return [command[0],f'-DCONDITIONED_MOMENT_BLOCK={block}',*command[1:]]


def main():
    records={}
    for target in ('host','sanitizer','arm'):
        record=module.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text());out=path.parent
        for block in (32,64):
            if block==32:
                # The base fused binary and moment unit are the block-32 artifacts.
                continue
            san=target=='sanitizer';fused=f'fused_quadratic_b{block}_{target}'
            command=with_block(module.builder.link_command(out,target,
                ['fused_probe.c','proposal_core.c'],fused,san,2),block)
            receipt['commands'].append(module.builder.run(command));receipt['binaries'][fused]=module.builder.sha(out/fused)
            unit=f'test_quadratic_b{block}_{target}'
            command=with_block(module.builder.link_command(out,target,
                ['test_moment_accuracy.c'],unit,san,0),block)
            receipt['commands'].append(module.builder.run(command));receipt['binaries'][unit]=module.builder.sha(out/unit)
            if target!='arm':
                run=subprocess.run([str(out/unit)],capture_output=True,text=True,check=True)
                receipt['units'].append({'binary':unit,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(schema='arm-conditioned-quadratic-build/v1',baseline='../2026_09_29_arm_wave4_combined',
            conditioned_model='degree-two block Taylor screen',conditioned_blocks=[32,64],
            scientific_scope='41 frequencies and 16 frames retained; no near-max FP64 recheck in base; final GLRT FP64 unchanged')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':record['receipt'],'sha256':module.builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-conditioned-quadratic-matrix/v1','builds':records},indent=2)+'\n')


if __name__=='__main__':main()
