"""Audit the unchanged12-scan Laplace expansion, then score reference error."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from nonlinear_laplace_adapter import observed_information
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'nonlinear-laplace-expansion-v1'
    freeze = directory/'sources.json'
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    batch = json.loads((directory/'batch.json').read_text())
    assert [r['unit_id'] for r in batch['launches']] == frozen['ordered_units']
    rows, states = [], {}
    for launch in batch['launches']:
        unit = launch['unit_id']
        path = directory/(unit+'.json')
        errors, receipt, fine_gain = [], {}, None
        try:
            assert launch == json.loads(path.with_suffix('.launch.json').read_text())
            assert launch['expansion_freeze_sha256'] == digest(freeze)
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 60.
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit
            assert receipt['source_freeze_sha256'] == frozen['pilot_freeze_sha256']
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            for key in ['inputs', 'height', 'observations']:
                assert receipt[key] == parent[key]
            scan, height, ports = prepare(unit)
            assert scan.inputs == receipt['inputs'] and height.input_bindings == receipt['height']
            assert [list(p.observation_ids) for p in ports] == receipt['observations']
            before = np.asarray(parent['best']['mean'])
            after = np.asarray(receipt['candidate_mean'])
            assert np.all(np.isfinite(after)) and np.linalg.norm(after[:2]) <= 250.
            assignments = [int(np.argmax(p.score_all(before))) for p in ports]
            assert receipt['assignments'] == assignments
            labels = sorted({i for p, i in zip(ports, assignments, strict=True)
                             if i < p.candidate_count})
            assert receipt['columns'] == [0, 1, 2, 3, 4, *(5+i for i in labels)]
            changes = sum(int(np.argmax(p.score_all(after))) != i
                          for p, i in zip(ports, assignments, strict=True))
            assert changes == receipt['assignment_changes']
            g = np.asarray(receipt['half_logdet_position_gradients'])
            refinement = np.linalg.norm(g[0]-g[1])
            np.testing.assert_allclose(refinement, receipt['gradient_refinement_norm'])
            numerical_ok = refinement <= max(.001, .02*np.linalg.norm(g[1]))
            assert numerical_ok == receipt['numerical_ok']
            np.testing.assert_allclose(after[:2]-before[:2], receipt['proposed_step_km'], atol=1e-9)
            assert np.linalg.norm(after[:2]-before[:2]) <= 2.+1e-9
            fine_scores = []
            stored_scores = [receipt['baseline_score_profile_logdet'],
                             receipt['candidate_score_profile_logdet']]
            for state, stored in zip([before, after], stored_scores, strict=True):
                precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
                profile = .5*(precision*state)@state-sum(
                    p.score_selected(state, i) for p, i in zip(ports, assignments, strict=True))
                assert abs(profile-stored[1]) < 1e-8
                assert abs(stored[0]-stored[1]-.5*stored[2]) < 1e-8
                matrix = observed_information(ports, assignments, state,
                                               np.asarray(receipt['columns'][2:]), step=.0025)
                chol = np.linalg.cholesky(matrix)
                fine_scores.append(float(profile+np.log(np.diag(chol)).sum()))
            gain = stored_scores[0][0]-stored_scores[1][0]
            fine_gain = fine_scores[0]-fine_scores[1]
            assert abs(gain-fine_gain) < max(1e-5, .01*abs(gain))
            accept = bool(receipt['nuisance_converged'] and changes == 0
                          and numerical_ok and gain > 0)
            assert receipt['candidate_accepted'] == accept
            selected = after if accept else before
            np.testing.assert_equal(receipt['selected_mean'], selected)
            states[unit] = (before[:2], selected[:2])
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, valid=not errors, audit_errors=errors,
                         candidate_accepted=receipt.get('candidate_accepted'),
                         fine_laplace_gain=fine_gain, runtime_s=launch['elapsed_seconds'],
                         cpu_s=receipt.get('cpu_seconds'), baseline_error_m=None, error_m=None))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('laplace_expansion_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            before, after = states[row['unit']]
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*before), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*after), reference.REFERENCE)
    valid = [r for r in rows if r['valid']]
    # Failed audits remain in denominator; do not publish success-only quantiles.
    complete = len(valid) == len(rows)
    result = dict(
        planned=len(rows), valid=len(valid), failed=len(rows)-len(valid), denominator=len(rows),
        proposals_selected=sum(r['candidate_accepted'] is True for r in valid),
        improved=sum(r['error_m'] < r['baseline_error_m'] for r in valid),
        baseline_median_error_m=float(np.median([r['baseline_error_m'] for r in valid]))
        if complete else None,
        median_error_m=float(np.median([r['error_m'] for r in valid])) if complete else None,
        baseline_p90_error_m=float(np.percentile([r['baseline_error_m'] for r in valid], 90))
        if complete else None,
        p90_error_m=float(np.percentile([r['error_m'] for r in valid], 90)) if complete else None,
        within1000_m=sum(r['error_m'] <= 1000 for r in valid),
        within3000_m=sum(r['error_m'] <= 3000 for r in valid),
        median_diagnostic_runtime_s=float(np.median([r['runtime_s'] for r in rows])),
        maximum_diagnostic_runtime_s=max(r['runtime_s'] for r in rows),
        median_diagnostic_cpu_s=float(np.median([r['cpu_s'] for r in valid])),
        source_freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__), rows=rows,
        qualification='Unchanged one-step nonlinear Laplace correction on12 preselected exposed '
        'regression scans. Finer Hessian audit before reference scoring. Warm diagnostics only; '
        'no cold90s, held-out accuracy or calibrated uncertainty claim. No arm tuning.')
    output = HERE/'nonlinear-laplace-expansion-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
