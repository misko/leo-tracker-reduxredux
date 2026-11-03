"""Audit alternating search receipts and independent stationarity before geography."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from candidate_calibrated_cached_joint import CandidateJointObjective
from diagnose_candidate_reassociation import training_information
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'calibrated-alternating-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit, arm in frozen['pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, discrepancy = [], {}, None
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30
            assert launch['freeze_sha256'] == digest(freeze)
            assert launch['receipt_sha256'] == digest(path)
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['arm'] == arm
            assert receipt['converged'], receipt['reason']
            assert receipt['seconds'] < 30
            for name, expected in receipt['sources'].items():
                assert frozen['source_sha256'][name] == expected
            verify_sources(receipt['inputs'])
            parent_path = HERE/'calibrated-joint-v1'/(unit+'-candidate.json')
            if not parent_path.exists():
                parent_path = HERE/'calibrated-joint-expansion-v1'/(unit+'-candidate.json')
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            assert receipt['height'] == parent['height']
            assert receipt['inputs'] == parent['inputs']
            assignments = receipt['assignments']
            state = np.asarray(receipt['full_state'])
            clean, prior_gain = profile_unused_epochs(state, assignments, len(state)-5)
            assert prior_gain == 0 and np.array_equal(clean, state)
            assert np.linalg.norm(state[:2]) <= 250
            model = CandidateJointObjective(unit, state=receipt['metric_state'],
                                            assignments=assignments)
            assert model.columns.tolist() == receipt['columns']
            metric = training_information(model)
            assert np.allclose(metric, receipt['metric'], atol=1e-10, rtol=1e-10)
            point = state[model.columns]
            value, gradient = model.evaluate(point)
            assert abs(value-receipt['final_objective']) < 1e-7
            assert np.all(np.diff(receipt['history']) <= 1e-7)
            assert abs(value-receipt['history'][-1]) < 1e-7
            for fit in receipt['fits']:
                assert fit['converged'] and np.all(np.diff(fit['objectives']) <= 1e-7)
            assert all(abs(p['discrepancy']) < 1e-7 for p in receipt['profiles'])
            assert gradient@np.linalg.solve(metric, gradient) <= 1e-6
            finite = []
            for direction in np.eye(len(point))*.0005:
                a = model.evaluate(point+direction, gradient=False)[0]
                b = model.evaluate(point-direction, gradient=False)[0]
                finite.append((a-b)/.001)
            finite = np.asarray(finite)
            discrepancy = float(np.max(np.abs(finite-gradient)))
            assert discrepancy < .005 and finite@np.linalg.solve(metric, finite) < 1e-5
            if arm == 'candidate':
                assert receipt['reason'] == 'no_improving_best_alternative'
                final_trials = [t for t in receipt['trials']
                                if t['iteration'] == len(receipt['fits'])-1]
                tested = {t['track']: t for t in final_trials}
                assert len(tested) == len(final_trials)
                expected_tracks = set()
                for track, (port, old) in enumerate(zip(model.base.ports, assignments, strict=True)):
                    scores = np.asarray(port.score_all(state)).copy()
                    scores[old] = -np.inf
                    best = int(np.argmax(scores))
                    if not np.isfinite(scores[best]):
                        continue
                    expected_tracks.add(track)
                    assert tested[track]['identity'] == best
                    choices = list(assignments)
                    choices[track] = best
                    clean, _ = profile_unused_epochs(state, choices, len(state)-5)
                    proposal = CandidateJointObjective(unit, state=clean, assignments=choices,
                                                       context=model.base)
                    scalar = proposal.evaluate(proposal.initial, gradient=False)[0]
                    assert abs(scalar-tested[track]['after']) < 1e-7
                    assert abs(value-tested[track]['before']) < 1e-7
                    assert scalar >= value-1e-7
                assert set(tested) == expected_tracks
            if arm == 'control':
                assert assignments == parent['assignments']
                assert np.linalg.norm(state[:2]-np.asarray(parent['mean'][:2]))*1000 < .1
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
            reason=receipt.get('reason'), state=receipt.get('full_state'),
            initial=receipt.get('initial_full_state'), runtime_s=launch['elapsed_seconds'],
            cpu_s=receipt.get('cpu_s'), gradient_discrepancy=discrepancy,
            fit_rounds=len(receipt.get('fits', [])), trials=len(receipt.get('trials', [])),
            error_m=None, parent_error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('alternating_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            for key, point in [('error_m', row['state']), ('parent_error_m', row['initial'])]:
                row[key] = reference.distance_m(
                    reference.latlon_from_enu(*point[:2]), reference.REFERENCE)
        del row['state'], row['initial']
    baseline_path = HERE/'calibrated-joint-panel-v1.json'
    assert digest(baseline_path) == baseline_path.with_suffix('.sha256').read_text().strip()
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    candidates = [r for r in rows if r['arm'] == 'candidate']
    accepted = [r for r in candidates if r['valid']]
    comparisons = {}
    for label, values in [
        ('original_all_data', [baseline[r['unit']]['original_all_data_error_m'] for r in accepted]),
        ('fixed_identity_joint', [baseline[r['unit']]['calibrated_joint_error_m'] for r in accepted]),
        ('alternating', [r['error_m'] for r in accepted]),
    ]:
        comparisons[label] = dict(median_error_m=float(np.median(values)) if values else None,
            p90_error_m=float(np.percentile(values, 90)) if values else None)
    summary = dict(candidate_accepted_of_12=len(accepted),
        candidate_within_1000m_of_12=sum(r['error_m'] <= 1000 for r in accepted),
        candidate_within_3000m_of_12=sum(r['error_m'] <= 3000 for r in accepted),
        improved_over_fixed_identity=sum(r['error_m'] < r['parent_error_m'] for r in accepted),
        paired_accepted_units=[r['unit'] for r in accepted], paired_comparisons=comparisons,
        candidate_median_runtime_s=float(np.median([r['runtime_s'] for r in candidates])),
        candidate_max_runtime_s=max(r['runtime_s'] for r in candidates),
        candidate_median_cpu_s=float(np.median([r['cpu_s'] for r in candidates
                                              if r['cpu_s'] is not None])))
    result = dict(rows=rows, summary=summary, 
        baseline_evaluation_sha256=digest(baseline_path),
        planned=len(rows), valid=sum(r['valid'] for r in rows),
        freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
        qualification='Vectorized fixed-state proposal scoring, unchanged continuous objective. '
        'Fresh calibrated parents; no retries. '
        'Frozen excluded-dataset calibration. '
        'Broad best-alternative proposals on frozen12development scans, '
        'max12rounds/25s; '
        'exact unused epoch profiling. '
        'No-improvement means only tested best alternative per track, not all catalogue '
        'assignments. Failures retained in12scan denominator; paired quantiles conditional '
        'on acceptance. No cold64, independent validation or calibration claim.')
    output = HERE/'calibrated-alternating-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
