"""Audit saved T1-AT associations and every available independent position case.

Recompute scores without optimizing or modifying inference results. An incomplete
cohort is reported as incomplete; --require-complete also returns a failure code.
The audit does not turn conditional associations into identity validation.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import subset_positions as positions
from cohort import digest

SCANS = ['A', 'B'] + [f'N{i:02}' for i in range(1, 17)]
ASSOCIATIONS = Path('/srv/bulk/leo/t1-at-v1-replication-20261004')
CASES = ['all-100'] + [f'{r}-{f}' for r in ('rms', 'support', 'glrt') for f in (25, 50, 75)]
CASES += [f'rms-cut-{v}' for v in (50, 100, 300, 600)]


def folder(scan):
    return ASSOCIATIONS / ('replayed-ab-verified' if scan in ('A', 'B') else
                           'attempt2' if scan in ('N01', 'N02') else 'remaining') / scan


def audit():
    positions.enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from position_direct import coordinate

    receipts, checked, missing = [], [], []
    for scan in SCANS:
        source = folder(scan)
        root = positions.ROOT / scan
        metadata = json.loads((root / 'input.json').read_text())
        assert metadata['input_sha256'] == digest((root / 'input.npz').read_bytes()), scan
        with np.load(root / 'input.npz') as arrays:
            full = SimpleNamespace(**{k: arrays[k].copy() for k in arrays.files})
        association = None
        for arm in ('fitted-c', 'zero-c'):
            path = source / f'{arm}.json'
            result = json.loads(path.read_text())
            final = result['final']
            denominator = result['summary']['denominator']
            assignments = final['assignments']
            assert len(assignments) == final['assigned']
            assert len({r['row_index'] for r in assignments}) == len(assignments)
            assert final['assigned'] + final['unassigned'] == denominator
            assert final['objective'] == final['assigned'] - 10 * final['satellites']
            assert final['objective'] >= result['initial']['objective']
            assert all(abs(r['residual_hz']) <= 600 for r in assignments)
            assert all(abs(r['offset_s']) <= 20 for r in final['selected'])
            assert len(final['selected']) == final['satellites']
            receipts.append(dict(scan=scan, arm=arm, assigned=final['assigned'],
                                 denominator=denominator, source=str(path),
                                 sha256=digest(path.read_bytes())))
            if arm == 'fitted-c':
                association = {r['row_index']: r['catalog_number'] for r in assignments}
        assert association == dict(zip(map(int, full.original_rows), map(int, full.owners))), scan
        assert len(set(full.group)) == len(full.times), scan
        assert set(full.numbers) == set(full.owners), scan
        all_case = json.loads((root / 'all-100.json').read_text())
        rms = {int(n): v for n, v in all_case['roof_owner_rms_hz'].items()}
        for case in CASES:
            path = root / f'{case}.json'
            if not path.exists():
                missing.append(f'{scan}/{case}')
                continue
            try:
                result = json.loads(path.read_text())
            except json.JSONDecodeError:
                missing.append(f'{scan}/{case}')
                continue
            if case == 'all-100':
                numbers, keep = list(full.numbers), np.ones(len(full.times), bool)
            else:
                numbers, keep = positions.choose(full.owners, full.original_rows, full.margin,
                                                 full.times, rms, result['ranking'], result['fraction'])
            assert result['windows'] == int(keep.sum())
            assert result['candidates'] == len(numbers)
            if not numbers:
                assert result['state'] == 'empty-subset' and not result['arms']
                checked.append(dict(scan=scan, case=case, state='empty-subset', source=str(path),
                                    sha256=digest(path.read_bytes())))
                continue
            assert result['numbers'] == numbers
            assert result['original_rows'] == full.original_rows[keep].tolist()
            assert set(result['arms']) == {'fitted-c', 'zero-c'}
            data = copy.copy(full)
            columns = np.array([int(np.flatnonzero(full.numbers == n)[0]) for n in numbers])
            for key in ('times', 'measured', 'rf', 'receiver', 'channel', 'group', 'margin',
                        'original_rows', 'owners'):
                setattr(data, key, getattr(full, key)[keep].copy())
            data.numbers = full.numbers[columns]
            data.position, data.velocity = full.position[columns], full.velocity[columns]
            data.initial = np.r_[full.initial[:6], full.initial[6 + columns]]
            objective = CalibrationObjective(data, data.initial, np.arange(len(numbers)), False, 12.)
            objective.center = metadata['rf_center_hz']
            objective.features = ((data.rf - objective.center) / 1e9)[:, None]
            objective.likelihood.features = objective.features
            objective.base.minimum_shift_s = max(objective.base.minimum_shift_s, -20.)
            objective.base.maximum_shift_s = min(objective.base.maximum_shift_s, 20.)
            objective.base.deadline = float('inf')
            errors = []
            for arm, outcome in result['arms'].items():
                best = outcome['best']
                assert best['objective'] <= min(r['objective'] for r in outcome['records']) + 1e-7
                assert outcome['converged'] == (best['success'] and not best['fixed_location'])
                for label in ('roof', 'best'):
                    saved = outcome[label]
                    vector = np.asarray(saved['vector'])
                    assert np.linalg.norm(saved['point_km']) <= 2 + 1e-8
                    np.testing.assert_allclose(vector[:2], coordinate(saved['point_km']), atol=1e-8, rtol=0)
                    assert abs(vector[6]) <= 10 + 1e-8
                    assert np.max(abs(np.asarray(saved['parameters'])[6:])) <= 20 + 1e-8
                    assert abs(vector[-1]) <= 5000 + 1e-8
                    if arm == 'zero-c': assert vector[-1] == 0
                    score, _ = objective.evaluate(vector)
                    error = abs(score - saved['objective'])
                    assert error < 1e-7, (scan, case, arm, label, error)
                    errors.append(error)
            checked.append(dict(scan=scan, case=case, state='audited', windows=result['windows'],
                                satellites=len(numbers), max_score_reconstruction_error=max(errors),
                                source=str(path), sha256=digest(path.read_bytes())))
        print(scan, 'audited', sum(r['scan'] == scan for r in checked), '/', len(CASES), flush=True)
    result = dict(scope=__doc__, created_utc=datetime.now(timezone.utc).isoformat(),
                  complete=not missing, expected_cases=len(SCANS) * len(CASES),
                  missing=missing, associations=receipts, position_cases=checked,
                  implementation_sha256=digest(Path(__file__).read_bytes()))
    positions.save(positions.HERE / 'cohort-audit.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    result = audit()
    print('Audited', len(result['position_cases']), '/', result['expected_cases'],
          'complete=', result['complete'])
    if args.require_complete and not result['complete']:
        raise SystemExit('Cohort remains incomplete')
