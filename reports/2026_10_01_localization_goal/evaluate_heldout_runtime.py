"""Audit held-out completion and runtime without loading a location reference."""
import argparse
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from heldout_adapter import prepare_heldout
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze_path = HERE/'heldout-baseline-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    rows = []
    for unit in freeze['ordered_units']:
        launches = list((HERE/'heldout-baseline-v1').glob('batch-*/'+unit+'.launch.json'))
        if not launches:
            rows.append(dict(unit=unit, accepted=False, status='not_finished', error_m=None))
            continue
        assert len(launches) == 1
        launch = json.loads(launches[0].read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        path = launches[0].with_name(unit+'.json')
        receipt, errors = {}, []
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit and receipt['arm'] == 'hard'
                assert receipt['config'] == dict(
                    prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                    iterations_per_seed=64, acquisition_limit_s=50.,
                    internal_deadline_s=85., external_limit_s=90.)
                for filename, expected in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == expected
                scan, height, ports = prepare_heldout(unit)
                assert receipt['inputs'] == scan.inputs
                assert receipt['height'] == height.input_bindings
                assert receipt['observations'] == [list(p.observation_ids) for p in ports]
            except (AssertionError, KeyError, OSError, ValueError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, accepted=not failures, status=receipt.get('status', 'missing'),
                         audit_errors=errors, acceptance_failures=failures,
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         error_m=None, receipt_sha256=launch.get('receipt_sha256')))
    times = [r['runtime_s'] for r in rows if 'runtime_s' in r]
    result = dict(planned=16, finished=len(times), accepted=sum(r['accepted'] for r in rows),
                  median_runtime_s=float(np.median(times)) if times else None,
                  maximum_runtime_s=max(times) if times else None,
                  qualification='Reference-blind runtime/completion audit only. '
                  'Geographic accuracy and uncertainty coverage remain unscored pending reference.',
                  freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__), rows=rows)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
