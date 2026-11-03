"""Independently verify group scores and full-objective selection before GPS scoring."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'profiled-identity-v1'
    freeze = directory/'sources.json'
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    rows, states = [], {}
    for unit in frozen['ordered_units']:
        path = directory/(unit+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, proposals = [], {}, []
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 60.
            assert launch['source_freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['source_freeze_sha256'] == digest(freeze)
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            scan, height, ports = prepare(unit)
            assert receipt['inputs'] == scan.inputs == parent['inputs']
            assert receipt['height'] == height.input_bindings == parent['height']
            assert receipt['observations'] == parent['observations']
            assert receipt['observations'] == [list(p.observation_ids) for p in ports]
            state = np.asarray(parent['best']['mean'])
            assigned = [int(np.argmax(p.score_all(state))) for p in ports]
            assert assigned == receipt['assignments']
            precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
            baseline = float(.5*(precision*state)@state-sum(
                p.score_selected(state, i) for p, i in zip(ports, assigned, strict=True)))
            assert abs(baseline-receipt['baseline_objective']) < 1e-8
            best_state, best_value, selected = state, baseline, None
            previous_gain = np.inf
            for row in receipt['proposals']:
                proposal = row['proposal']
                assert proposal['conditional_gain'] <= previous_gain
                previous_gain = proposal['conditional_gain']
                if row['status'] == 'not_started_budget':
                    proposals.append(dict(rank=row['rank'], status=row['status']))
                    continue
                source, target = proposal['source'], proposal['target']
                assert source in assigned and target not in assigned
                tracks = [j for j, i in enumerate(assigned) if i == source]
                assert tracks == proposal['track_indices']
                gains = []
                for epoch in receipt['epoch_grid_s']:
                    seed = state.copy()
                    seed[5+source], seed[5+target] = 0., epoch
                    new_log = sum(ports[j].score_selected(seed, target) for j in tracks)
                    old_log = sum(ports[j].score_selected(state, source) for j in tracks)
                    gains.append(float(new_log-old_log-2*epoch**2
                                       +2*state[5+source]**2+2*state[5+target]**2))
                assert int(np.argmax(gains)) == proposal['epoch_index']
                assert abs(max(gains)-proposal['conditional_gain']) < 1e-7
                after = np.asarray(row['mean'])
                assert np.all(np.isfinite(after)) and np.linalg.norm(after[:2]) <= 250.
                final_assignments = [int(np.argmax(p.score_all(after))) for p in ports]
                signal_log = sum(p.score_selected(after, i) for p, i in
                                 zip(ports, final_assignments, strict=True))
                value = float(.5*(precision*after)@after-signal_log)
                assert abs(value-row['objectives'][-1]) < 1e-6
                changes = sum(a != b for a, b in zip(assigned, final_assignments, strict=True))
                assert changes == row['final_assignment_changes']
                if row['converged'] and value < best_value-1e-6:
                    best_state, best_value, selected = after, value, row['rank']
                proposals.append(dict(rank=row['rank'], converged=row['converged'],
                                      conditional_gain=proposal['conditional_gain'],
                                      original_objective_gain=baseline-value,
                                      final_assignment_changes=changes))
            assert selected == receipt['selected_proposal']
            assert abs(best_value-receipt['selected_objective']) < 1e-6
            np.testing.assert_equal(best_state, receipt['selected_mean'])
            states[unit] = (state[:2], best_state[:2])
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, valid=not errors, audit_errors=errors, proposals=proposals,
                         selected_proposal=receipt.get('selected_proposal'),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         baseline_error_m=None, selected_error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('identity_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            before, after = states[row['unit']]
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*before), reference.REFERENCE)
            row['selected_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*after), reference.REFERENCE)
    result = dict(planned=3, valid=sum(r['valid'] for r in rows), rows=rows,
                  evaluator_sha256=digest(__file__), source_freeze_sha256=digest(freeze),
                  qualification='Warm search on3 exposed development controls. Independent '
                  'single-row branch scores verify group ranking and final all-track objective '
                  'before reference read. Not cold90s performance, verified satellite identity, '
                  'exhaustive mode search or uncertainty calibration.')
    output = HERE/'profiled-identity-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
