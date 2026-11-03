"""Re-score archived A/B optima on the new inputs, without changing either run.

This is an optimizer diagnostic, not an extra restart granted only to A/B.
Only identical frozen observations and candidate banks are comparable.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import subset_positions as positions
from cohort import digest


def audit():
    positions.enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective

    historical = positions.HERE.parent / '2026_10_04_ds13_association_review/subset-position-search'
    rows = []
    for scan in ('A', 'B'):
        root = positions.ROOT / scan
        metadata = json.loads((root / 'input.json').read_text())
        with np.load(root / 'input.npz') as arrays:
            full = SimpleNamespace(**{k: arrays[k].copy() for k in arrays.files})
        for path in sorted(root.glob('*.json')):
            if path.name == 'input.json' or path.name.endswith('-partial.json'):
                continue
            current = json.loads(path.read_text())
            for arm, result in current['arms'].items():
                old_path = historical / f'{scan}-{current["case_id"]}-{arm}.json'
                if not old_path.exists():
                    continue
                old = json.loads(old_path.read_text())
                same_rows = set(old['subset']['original_rows']) == set(current['original_rows'])
                same_bank = old['subset']['numbers'] == current['numbers']
                row = dict(scan=scan, case=current['case_id'], arm=arm,
                           same_rows=same_rows, same_bank=same_bank,
                           historical_distance_m=old['distance_m'],
                           new_distance_m=result['distance_m'],
                           historical_saved_score=old['best']['objective'],
                           new_saved_score=result['best']['objective'],
                           sources={str(p): digest(p.read_bytes()) for p in (path, old_path)})
                if same_rows and same_bank:
                    data = copy.copy(full)
                    keep = np.isin(full.original_rows, current['original_rows'])
                    columns = np.array([int(np.flatnonzero(full.numbers == n)[0])
                                        for n in current['numbers']])
                    for key in ('times', 'measured', 'rf', 'receiver', 'channel', 'group',
                                'margin', 'original_rows', 'owners'):
                        setattr(data, key, getattr(full, key)[keep].copy())
                    data.numbers = full.numbers[columns]
                    data.position, data.velocity = full.position[columns], full.velocity[columns]
                    data.initial = np.r_[full.initial[:6], full.initial[6 + columns]]
                    objective = CalibrationObjective(data, data.initial,
                                                     np.arange(len(columns)), False, 12.)
                    objective.center = metadata['rf_center_hz']
                    objective.features = ((data.rf - objective.center) / 1e9)[:, None]
                    objective.likelihood.features = objective.features
                    objective.base.minimum_shift_s = max(objective.base.minimum_shift_s, -20.)
                    objective.base.maximum_shift_s = min(objective.base.maximum_shift_s, 20.)
                    objective.base.deadline = float('inf')
                    for label, best in [('historical', old['best']), ('new', result['best'])]:
                        value, _ = objective.evaluate(np.asarray(best['vector']))
                        row[f'{label}_reevaluated_score'] = float(value)
                        assert abs(value - best['objective']) < 1e-7, row
                    row['new_minus_historical_score'] = (
                        row['new_reevaluated_score'] - row['historical_reevaluated_score'])
                    row['historical_better_score'] = row['new_minus_historical_score'] > 1e-5
                    row['new_better_score'] = row['new_minus_historical_score'] < -1e-5
                rows.append(row)
    positions.save(positions.HERE / 'historical-position-audit.json', dict(
        scope=__doc__, implementation_sha256=digest(Path(__file__).read_bytes()), rows=rows))
    for row in rows:
        if row.get('historical_better_score') or row.get('new_better_score'):
            print(row['scan'], row['case'], row['arm'], row['new_minus_historical_score'])
    return rows


if __name__ == '__main__':
    audit()
