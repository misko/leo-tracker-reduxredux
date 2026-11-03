"""Audit the bounded deletion-and-restoration search without geographic truth."""
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'deletion-bridge-v1'
    source_path = directory/'sources.json'
    sources = json.loads(source_path.read_text())
    verify_sources(sources['source_sha256'])
    original_path = HERE/'regression-v1-freeze.json'
    assert digest(original_path) == original_path.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original_path.read_text())['source_sha256'])
    batch = json.loads((directory/'batch.json').read_text())
    assert [r['unit_id'] for r in batch['launches']] == sources['ordered_units']
    rows = []
    for launch in batch['launches']:
        unit = launch['unit_id']
        path = directory/(unit+'.json')
        errors, receipt = [], {}
        try:
            assert launch == json.loads(path.with_suffix('.launch.json').read_text())
            assert launch['source_freeze_sha256'] == digest(source_path)
            assert launch['returncode'] == 0 and not launch['timed_out']
            assert launch['within_budget'] and launch['elapsed_seconds'] <= 30.
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['source_freeze_sha256'] == digest(source_path)
            assert receipt['unit'] == unit and receipt['converged']
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            assert digest(sources['parents'][unit]) == receipt['deletion_sha256']
            assert receipt['observations'] == parent['observations']
            assert receipt['track_count'] == len(parent['observations'])
            assert abs(receipt['original_objective']-parent['best']['objectives'][-1]) < 1e-6
            assert np.all(np.isfinite(receipt['mean']))
            np.testing.assert_allclose(receipt['displacement_from_original_m'], 1000*np.linalg.norm(
                np.asarray(receipt['mean'][:2])-np.asarray(parent['best']['mean'][:2])))
            assert np.max(np.diff(receipt['objectives'])) <= 1e-6
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        keys = ['initial_excursion_m', 'displacement_from_original_m', 'objective_gain',
                'assignment_changes', 'cpu_seconds']
        rows.append(dict(unit=unit, valid=not errors, audit_errors=errors,
                         runtime_s=launch['elapsed_seconds'],
                         **{k: receipt.get(k) for k in keys}))
    valid = [r for r in rows if r['valid']]
    result = dict(
        planned=len(rows), valid=len(valid), failures=len(rows)-len(valid),
        meaningful_objective_improvements=sum(r['objective_gain'] > 1e-6 for r in valid),
        maximum_final_displacement_m=max(r['displacement_from_original_m'] for r in valid),
        median_runtime_s=float(np.median([r['runtime_s'] for r in rows])),
        maximum_runtime_s=max(r['runtime_s'] for r in rows),
        median_cpu_s=float(np.median([r['cpu_seconds'] for r in valid])),
        source_freeze_sha256=digest(source_path), evaluator_sha256=digest(__file__),
        decision='Do not add this bridge to cold acquisition: no meaningful original-objective '
        'improvement on these five checks. Return within centimeters despite excursions up to14km. '
        'This tests one restart construction, not all modes or identity alternatives. '
        'No geographic selection, accuracy gain, uncertainty recalibration, or cold runtime claim.',
        rows=rows)
    output = HERE/'deletion-bridge-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
