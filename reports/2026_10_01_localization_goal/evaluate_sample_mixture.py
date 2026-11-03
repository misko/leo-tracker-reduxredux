"""Audit sample-mixture likelihoods, parity and gradients before geographic scoring."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources
from sample_mixture_adapter import SampleMixturePort

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'sample-mixture-v1'
    freeze = directory/'sources.json'
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    rows, states = [], {}
    for unit, arm in frozen['ordered_pairs']:
        path = directory/(unit+'-'+arm+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt, derivative_error = [], {}, None
        try:
            assert launch['returncode'] == 0 and launch['within_budget']
            assert not launch['timed_out'] and launch['elapsed_seconds'] <= 30.
            assert launch['source_freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            assert digest(path) == path.with_suffix('.sha256').read_text().strip()
            receipt = json.loads(path.read_text())
            assert receipt['unit'] == unit and receipt['arm'] == arm
            assert receipt['source_freeze_sha256'] == digest(freeze)
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == receipt['parent_sha256']
            parent = json.loads(parent_path.read_text())
            scan, height, ports = prepare(unit)
            assert receipt['inputs'] == scan.inputs == parent['inputs']
            assert receipt['height'] == height.input_bindings == parent['height']
            assert receipt['observations'] == parent['observations']
            assert receipt['observations'] == [list(p.observation_ids) for p in ports]
            before = np.asarray(parent['best']['mean'])
            after = np.asarray(receipt['mean'])
            assert receipt['converged'] and np.all(np.isfinite(after))
            assert np.linalg.norm(after[:2]) <= 250.
            probability = 0. if arm == 'control' else .05
            assert receipt['probability'] == probability
            assert receipt['extra_raw_scale_variance_hz2'] == 1000.**2
            assignments = [int(np.argmax(p.score_all(before))) for p in ports]
            assert assignments == receipt['assignments']
            adapted = [SampleMixturePort(p, i, probability)
                       for p, i in zip(ports, assignments, strict=True)]
            precision = np.r_[0., 0., 1., np.full(len(after)-3, 4.)]

            def objective(x, adapted=adapted, assignments=assignments, precision=precision):
                return float(.5*(precision*x)@x-sum(
                    p.score_selected(x, i) for p, i in zip(adapted, assignments, strict=True)))

            assert abs(objective(after)-receipt['objectives'][-1]) < 1e-7
            gradient = precision*after
            for p, index in zip(adapted, assignments, strict=True):
                if index < p.candidate_count:
                    prediction = p.predict_selected(after, index)
                    gradient -= prediction.jacobian.T@np.linalg.solve(
                        prediction.covariance, p.observation-prediction.mean)
            direction = np.zeros_like(after)
            direction[:5] = [.3, -.2, .1, -.4, .2]
            finite = (objective(after+.001*direction)-objective(after-.001*direction))/.002
            derivative_error = abs(float(gradient@direction)-finite)
            assert derivative_error < 1e-4
            if arm == 'control':
                assert abs(receipt['objectives'][-1]-parent['best']['objectives'][-1]) < 1e-6
                assert receipt['position_change_m'] < .1
            states[(unit, arm)] = (before[:2], after[:2])
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        rows.append(dict(unit=unit, arm=arm, valid=not errors, audit_errors=errors,
                         gradient_directional_error=derivative_error,
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         baseline_error_m=None, error_m=None,
                         high_probability_samples=receipt.get('samples_with_posterior_above_half')))
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('sample_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['valid']:
            before, after = states[(row['unit'], row['arm'])]
            row['baseline_error_m'] = reference.distance_m(
                reference.latlon_from_enu(*before), reference.REFERENCE)
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*after), reference.REFERENCE)
    result = dict(planned=6, valid=sum(r['valid'] for r in rows), rows=rows,
                  source_freeze_sha256=digest(freeze), evaluator_sha256=digest(__file__),
                  qualification='Three exposed development scans, paired warm ablations. '
                  'Normalized likelihood/gradient and zero-mask controls audited before reference '
                  'scoring. No cold90s, held-out, calibrated outlier or uncertainty claim.')
    output = HERE/'sample-mixture-v1-evaluation.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
