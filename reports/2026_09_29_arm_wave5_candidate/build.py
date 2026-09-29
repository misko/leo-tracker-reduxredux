#!/usr/bin/env python3
"""Build the isolated .312-rate-gate plus degree-one/block-32 candidate."""
import importlib.util,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_rate_coarse_gate'
spec=importlib.util.spec_from_file_location('rate_gate_builder',BASE/'build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
builder.ROOT=ROOT;builder.SOURCE=ROOT/'sources'
builder.THRESHOLDS={'2500000':.312,'5000000':.150,'7500000':.175,'10000000':.152}


def main():
    records={}
    for target in ('host','sanitizer','arm'):
        record=builder.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text())
        receipt.update(schema='arm-wave5-candidate-build/v1',
            composition_sources={
                'rate_gate':'../2026_09_29_arm_rate_coarse_gate/sources-312',
                'conditioned':'../2026_09_29_arm_conditioned_low_order degree1/block32'},
            conditioned_degree=1,conditioned_block=32,
            scientific_scope='all rate-gated candidates retain 16 conditioned frames and 41 bins; final GLRT FP64')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':record['receipt'],'sha256':builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-wave5-candidate-matrix/v1','builds':records},indent=2)+'\n')


if __name__=='__main__':main()
