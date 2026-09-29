#!/usr/bin/env python3
"""Build the Wave3 fine-input FP32/NEON preparation experiment."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / '2026_09_29_arm_resampled_omit_fused'

spec = importlib.util.spec_from_file_location('base_builder', BASE/'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
builder.ROOT = ROOT
builder.SOURCE = ROOT/'sources'


def main():
    records = {}
    for target in ('host', 'sanitizer', 'arm'):
        record = builder.build(target)
        receipt_path = ROOT/record['receipt']
        receipt = json.loads(receipt_path.read_text())
        out = receipt_path.parent
        name = f'cohort_probe_{target}'
        command = builder.link_command(out, target, ['cohort_probe.c'], name,
                                       target == 'sanitizer', 2)
        receipt['commands'].append(builder.run(command))
        receipt['binaries'][name] = builder.sha(out/name)
        receipt.update(
            schema='arm-fine-input-neon-build/v1',
            fine_input='coarse FP32 sample mirror times cached scaled FP32 template; ARM NEON four complex lanes',
            fine_energy='existing FP64 coarse prefix differences over unchanged active symbols',
            scientific_scope='fine estimator input approximation only; original FFT lengths/grid and FP64 final GLRT',
        )
        receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
        records[target] = {'receipt': record['receipt'],
                           'sha256': builder.sha(receipt_path)}
    (ROOT/'build-manifest.json').write_text(json.dumps({
        'schema':'arm-fine-input-neon-matrix/v1', 'builds':records}, indent=2)+'\n')


if __name__ == '__main__':
    main()
