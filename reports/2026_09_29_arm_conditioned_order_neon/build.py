#!/usr/bin/env python3
"""Build the Wave3 conditioned moment-order NEON experiment."""
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'2026_09_29_arm_resampled_omit_fused'
spec=importlib.util.spec_from_file_location('base_builder',BASE/'build.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
builder.ROOT=ROOT;builder.SOURCE=ROOT/'sources'


def main():
    records={}
    for target in ('host','sanitizer','arm'):
        record=builder.build(target)
        receipt_path=ROOT/record['receipt'];receipt=json.loads(receipt_path.read_text())
        receipt.update(
            schema='arm-conditioned-order-neon-build/v1',
            runner='Wave3 fused resampled/omit-power/rank-only/boundary-gate pipeline',
            conditioned_accumulation='order zero scalar; orders one through four packed in four ARM NEON lanes',
            delta_powers='per-block cache generated with sequential FP32 multiplication',
            scientific_scope='moment accumulation order only; 41-frequency evaluation, exact rechecks and FP64 final GLRT unchanged')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':record['receipt'],'sha256':builder.sha(receipt_path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({
        'schema':'arm-conditioned-order-neon-matrix/v1','builds':records},indent=2)+'\n')


if __name__=='__main__':main()
