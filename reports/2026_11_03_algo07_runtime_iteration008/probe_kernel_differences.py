"""Compare original and optimized contractions on identical real joint inputs."""

import argparse
import hashlib
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import numpy as np

from leo.analysis.research import joint_predictive_families as kernel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    baseline = Path('/opt/leo-fast-graph/e67f67484c4f54316b33dfd8e12f6e68d09d1e13')
    path = baseline/'src/leo/analysis/research/joint_predictive_families.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        'dbf7f397753cf91f764c75630e208bb2162a5ce9e2c69305537ce8ba53385065')
    spec = importlib.util.spec_from_file_location('original_joint_kernel', path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    candidate = kernel.two_family_phase_evidence
    rows = []
    saved = False

    def compare(*inputs, **kwargs):
        nonlocal saved
        a = reference.two_family_phase_evidence(*inputs, **kwargs)
        b = candidate(*inputs, **kwargs)
        differences = []
        for key in a:
            left, right = a[key], b[key]
            pairs = zip(left, right, strict=True) if key in (
                'phase_marginals', 'orbital_map_mean') else [(left, right)]
            for i, (x, y) in enumerate(pairs):
                if not np.array_equal(x, y):
                    differences.append(dict(field=key, part=i,
                                            max_absolute=float(np.max(np.abs(np.asarray(x)-y)))))
        rows.append(dict(call=len(rows), differences=differences))
        if differences and not saved:
            values = {'base_covariance': inputs[2]}
            for name, value in zip(('observed', 'means', 'modes', 'log_priors', 'visible'),
                                    (inputs[0], inputs[1], *inputs[3:]), strict=True):
                values.update({f'{name}_{i}': x for i, x in enumerate(value)})
            np.savez_compressed(args.output/'first-difference.npz', **values)
            saved = True
        return b

    kernel.two_family_phase_evidence = compare
    command = json.loads(args.receipt.read_text())['command'][2:]
    command[command.index('--output')+1] = str(args.output/'probe')
    sys.argv = command
    runpy.run_path(command[0], run_name='__main__')
    (args.output/'kernel-comparison.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(dict(calls=len(rows),
                          differing_calls=sum(bool(r['differences']) for r in rows))))


if __name__ == '__main__':
    main()
