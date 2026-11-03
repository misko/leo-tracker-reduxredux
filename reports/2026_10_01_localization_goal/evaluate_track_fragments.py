"""Audit cold partition pilots before reading reference coordinates."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources
from run_track_fragments import prepare

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'track-fragments-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows, states = [], {}
    for unit in frozen['units']:
        path = directory/(unit+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, changed = [], {}, None
        try:
            assert launch['freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                'prediction_sha256']
            receipt = json.loads(path.read_text())
            assert receipt['unit_id'] == unit and receipt['arm'] == 'hard'
            for filename, expected in receipt['source_sha256'].items():
                assert frozen['source_sha256'][filename] == expected, filename
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            parent_seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
            assert digest(parent_path) == parent_seal['prediction_sha256']
            parent = json.loads(parent_path.read_text())
            assert receipt['config'] == parent['config']
            scan, height, ports = prepare(unit)
            assert receipt['inputs'] == scan.inputs
            verify_sources(receipt['inputs'])
            assert receipt['height'] == height.input_bindings == parent['height']
            assert receipt['observations'] == [list(p.observation_ids) for p in ports]
            assert receipt['observations'][:len(parent['observations'])] == parent['observations']
            ids = [v for p in ports for v in p.observation_ids]
            assert len(ids) == len(set(ids))
            changed = len(set(map(tuple, receipt['observations']))
                          - set(map(tuple, parent['observations'])))
            best = receipt['best']
            state = np.asarray(best['mean'])
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            objective = .5*(precision*state)@state-sum(np.max(p.score_all(state)) for p in ports)
            assert abs(objective-best['objectives'][-1]) < 1e-6
            states[unit] = (parent['best']['mean'][:2], state[:2])
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, accepted=not failures, failures=failures, audit_errors=errors,
                         changed_selected_tracks=changed,
                         retained_tracks=len(receipt.get('observations', [])),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         baseline_error_m=None, error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('partition_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            before, after = states[row['unit']]
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*before), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*after), reference.REFERENCE)
    result = dict(planned=3, accepted=sum(r['accepted'] for r in rows), rows=rows,
                  source_freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
                  qualification='Three exposed development pilots, independent fresh acquisition. '
                  'No held-out or uncertainty calibration claim. Original observations retained; '
                  'Source-disjoint fragments added. Objectives cannot rank arms. '
                  'Failures retained.')
    output = HERE/'track-fragments-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
