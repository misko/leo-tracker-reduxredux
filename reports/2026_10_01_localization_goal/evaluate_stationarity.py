"""Verify and summarize all fixed-state stationarity diagnostics, without GPS."""
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'stationarity-v1'
    bindings = json.loads((directory/'sources.json').read_text())
    verify_sources(bindings)
    freeze_path = HERE/'regression-v1-freeze.json'
    freeze = json.loads(freeze_path.read_text())
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    verify_sources(freeze['source_sha256'])
    batch = json.loads((directory/'batch.json').read_text())
    assert batch['original_freeze_sha256'] == digest(freeze_path)
    assert [row['unit_id'] for row in batch['launches']] == freeze['ordered_units']
    rows, failures = [], []
    for launch in batch['launches']:
        unit = launch['unit_id']
        if launch['returncode'] or launch['timed_out']:
            failures.append(unit)
            continue
        path = directory/(unit+'.json')
        assert digest(path) == launch['receipt_sha256']
        row = json.loads(path.read_text())
        assert row['unit'] == unit
        assert row['source_sha256'] == bindings[str(HERE/'diagnose_stationarity.py')]
        receipts = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert len(receipts) == 1 and digest(receipts[0]) == row['receipt_sha256']
        rows.append(row)
    summary = dict(planned=len(freeze['ordered_units']), valid=len(rows), failures=failures)
    for key in ['irls_decrement_squared', 'proposed_position_step_m',
                'unscaled_vs_scaled_step_norm', 'fixed_assignment_objective_gain',
                'equilibrated_condition', 'raw_condition', 'seconds']:
        values = [row[key] for row in rows]
        summary[key] = dict(median=float(np.median(values)), maximum=max(values))
    summary.update(
        batch_sha256=digest(directory/'batch.json'), evaluator_sha256=digest(__file__),
        qualification='Fixed-state local stationarity only. No refitting or GPS evaluation. '
                      'Tiny decrement cannot rule out alternative associations or distant modes. '
                      'Diagnostic runtime is separate from benchmark inference.', rows=rows)
    with (HERE/'stationarity-v1-evaluation.json').open('x') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
