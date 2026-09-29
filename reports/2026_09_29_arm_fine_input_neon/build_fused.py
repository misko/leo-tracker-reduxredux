#!/usr/bin/env python3
"""Build immutable fused-runner receipts without touching the first matrix."""
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent/'2026_09_29_arm_resampled_omit_fused'/'build.py'


def load_builder():
    source = BASE.read_text()
    old = "out=ROOT/'builds'/target"
    assert source.count(old) == 1
    source = source.replace(old, "out=ROOT/'builds-fused'/target")
    module = types.ModuleType('fine_input_fused_builder')
    module.__file__ = str(BASE)
    exec(compile(source, str(BASE), 'exec'), module.__dict__)
    module.ROOT = ROOT
    module.SOURCE = ROOT/'sources'
    return module


def main():
    builder = load_builder()
    records = {}
    for target in ('host', 'sanitizer', 'arm'):
        record = builder.build(target)
        # The imported builder reports paths relative to ROOT, which remain
        # correct after redirecting only its output directory.
        receipt_path = ROOT/'builds-fused'/target/'build-receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt.update(
            schema='arm-fine-input-neon-fused-build/v1',
            fine_input='coarse FP32 sample mirror times cached scaled FP32 template; ARM NEON four complex lanes',
            runner='Wave3 fused resampled/omit-power/rank-only/boundary-gate pipeline',
            scientific_scope='fine estimator input approximation only; original FFT lengths/grid and FP64 final GLRT',
        )
        receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
        records[target] = {'receipt':str(receipt_path.relative_to(ROOT)),
                           'sha256':builder.sha(receipt_path)}
    (ROOT/'build-fused-manifest.json').write_text(json.dumps({
        'schema':'arm-fine-input-neon-fused-matrix/v1', 'builds':records}, indent=2)+'\n')


if __name__ == '__main__':
    main()
