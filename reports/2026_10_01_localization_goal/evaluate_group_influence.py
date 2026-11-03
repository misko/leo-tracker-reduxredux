"""Summarize source-bound group influence without reading geographic truth."""
import json
from pathlib import Path

import numpy as np
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'group-influence-v1'
    bindings = json.loads((directory/'sources.json').read_text())
    verify_sources(bindings)
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    batch = json.loads((directory/'batch.json').read_text())
    assert batch['original_freeze_sha256'] == digest(freeze_path)
    assert [r['unit_id'] for r in batch['launches']] == freeze['ordered_units']
    rows, failures = [], []
    for launch in batch['launches']:
        unit = launch['unit_id']
        if launch['returncode'] or launch['timed_out']:
            failures.append(unit)
            continue
        path = directory/(unit+'.json')
        assert digest(path) == launch['receipt_sha256']
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        r = json.loads(path.read_text())
        assert r['unit'] == unit and r['source_sha256'] == bindings[
            str(HERE/'diagnose_group_influence.py')]
        assert r['kernel_sha256'] == bindings[
            str(HERE.parents[1]/'src/leo/analysis/localization_influence.py')]
        parents = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert len(parents) == 1 and digest(parents[0]) == r['parent_sha256']
        candidates = [g for g in r['groups'] if g['position_step_m'] is not None]
        largest = max(candidates, key=lambda g: g['position_step_m'])
        assert largest['candidate_index'] == r['largest_candidate_index']
        assert largest['position_step_m'] == r['maximum_predicted_shift_m']
        rows.append(dict(unit=unit, maximum_predicted_shift_m=largest['position_step_m'],
                         largest_norad_id=largest['norad_id'],
                         largest_group_track_count=largest['track_count'],
                         group_count=r['group_count'], invalid_deletions=r['invalid_deletions'],
                         seconds=r['quadratic_seconds'], receipt_sha256=digest(path)))
    pilots = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        path = HERE/('group-influence-'+unit+'.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        r = json.loads(path.read_text())
        assert r['source_sha256'] == bindings[str(HERE/'diagnose_group_influence.py')]
        assert r['kernel_sha256'] == bindings[
            str(HERE.parents[1]/'src/leo/analysis/localization_influence.py')]
        parents = list((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert len(parents) == 1 and digest(parents[0]) == r['parent_sha256']
        pilot = {k: v for k, v in r['refit'].items() if k not in ('mean', 'objectives')}
        pilot.update(unit=unit, predicted_shift_m=r['maximum_predicted_shift_m'],
                     total_seconds=r['seconds'], receipt_sha256=digest(path))
        pilots.append(pilot)
    shifts = [r['maximum_predicted_shift_m'] for r in rows]
    result = dict(
        planned=64, valid=len(rows), failures=failures,
        median_maximum_shift_m=float(np.median(shifts)),
        p90_maximum_shift_m=float(np.percentile(shifts, 90)), maximum_shift_m=max(shifts),
        scans_over_1000m=sum(x > 1000 for x in shifts),
        scans_over_3000m=sum(x > 3000 for x in shifts),
        scans_with_single_track_most_influential=sum(
            r['largest_group_track_count'] == 1 for r in rows),
        invalid_deletions=sum(r['invalid_deletions'] for r in rows),
        median_diagnostic_seconds=float(np.median([r['seconds'] for r in rows])),
        batch_sha256=digest(directory/'batch.json'), evaluator_sha256=digest(__file__),
        qualification='Reference-blind fixed-state sensitivity only. These are predicted shifts, '
        'not geographic errors or confidence radii. Local linearization can underestimate '
        'nonlinear deletion movement. Three bounded warm checks are not cold benchmark inference.',
        rows=rows, nonlinear_checks=pilots)
    with (HERE/'group-influence-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
