#!/usr/bin/env python3
"""Build the .312 rate gate with the sealed quadratic block-64 screen."""
import importlib.util,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_rate_coarse_gate'
spec=importlib.util.spec_from_file_location('rate_gate_builder',BASE/'build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
builder.ROOT=ROOT;builder.SOURCE=ROOT/'sources'
builder.THRESHOLDS={'2500000':.312,'5000000':.150,'7500000':.175,'10000000':.152}
base_command=builder.command


def block64_command(*args,**kwargs):
    command=base_command(*args,**kwargs)
    return [command[0],'-DCONDITIONED_MOMENT_BLOCK=64',*command[1:]]


builder.command=block64_command


def main():
    records={}
    for target in ('host','sanitizer','arm'):
        record=builder.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text())
        receipt.update(schema='arm-gate-quadratic-build/v1',
            composition_sources={'rate_gate':'../2026_09_29_arm_rate_coarse_gate/sources-312',
                'conditioned':'../2026_09_29_arm_conditioned_quadratic degree2/block64'},
            conditioned_degree=2,conditioned_block=64,
            scientific_scope='all rate-gated candidates retain 16 conditioned frames and 41 bins; final GLRT FP64')
        out=path.parent;name=f'test_sparse_peak_scan_{target}'
        command=builder.command(out,target,['test_sparse_peak_scan.c'],name,target=='sanitizer',0)
        receipt['commands'].append(builder.run(command));receipt['binaries'][name]=builder.sha(out/name)
        if target!='arm':
            unit=subprocess.run([str(out/name)],text=True,capture_output=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':unit.stdout,'stderr':unit.stderr})
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':record['receipt'],'sha256':builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-gate-quadratic-matrix/v1','builds':records},indent=2)+'\n')


if __name__=='__main__':main()
