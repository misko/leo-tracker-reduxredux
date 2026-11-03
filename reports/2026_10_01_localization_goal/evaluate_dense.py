"""Audit density pilots, including exact observation selection, before GPS."""
import importlib.util
import json
from pathlib import Path

from dense_adapter import dense_ports, prepare
from evaluate_regression import qualification
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    freeze_path = HERE/'dense-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    verify_sources(freeze['source_sha256'])
    baseline_path = HERE/'regression-v1-evaluation-64.json'
    assert digest(baseline_path) == (
        'sha256:97be104787783e3bb81d851ba8664f3a26ac93fe10b617aae605ad8b13372bd7')
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']}
    rows, states = [], {}
    for unit, count in freeze['ordered_pairs']:
        path = HERE/'dense-v1'/(unit+'-'+str(count)+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['freeze_sha256'] == digest(freeze_path)
        receipt, errors = {}, []
        if path.exists():
            try:
                assert digest(path) == launch['receipt_sha256']
                assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
                    'prediction_sha256']
                receipt = json.loads(path.read_text())
                assert receipt['unit_id'] == unit
                assert receipt['config'] == dict(
                    prior_radius_km=250., height_m_msl=30.48,
                    acquisition_max_points=8, fit_max_points=count,
                    seed_limit=3, iterations_per_seed=64, acquisition_limit_s=50.,
                    internal_deadline_s=85., external_limit_s=90.)
                for filename, expected in receipt['source_sha256'].items():
                    assert freeze['source_sha256'][filename] == expected
                scan, height, acquisition_ports = prepare(unit)
                ports = dense_ports(scan, height, count)
                assert receipt['inputs'] == scan.inputs
                assert receipt['height'] == height.input_bindings
                assert receipt['observations'] == [list(p.observation_ids) for p in ports]
                assert receipt['acquisition_observations'] == [
                    list(p.observation_ids) for p in acquisition_ports]
                ids = [i for p in ports for i in p.observation_ids]
                assert len(ids) == len(set(ids))
                for filename, expected in receipt['inputs'].items():
                    assert digest(filename) == expected
                previous = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
                assert digest(previous) == baseline[unit]['receipt_sha256']
                control = json.loads(previous.read_text())
                assert receipt['acquisition_observations'] == control['observations']
                # Acquisition timings differ; the actual proposals must match.
                assert receipt['proposal']['seeds'] == control['proposal']['seeds']
            except (AssertionError, KeyError, ValueError, FileNotFoundError) as error:
                errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        accepted = not failures
        rows.append(dict(unit=unit, max_points=count, accepted=accepted, audit_errors=errors,
                         acceptance_failures=failures, status=receipt.get('status', 'missing'),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         fit_observation_count=sum(map(len, receipt.get('observations', []))),
                         baseline_error_m=baseline[unit]['error_m'], error_m=None,
                         receipt_sha256=launch.get('receipt_sha256')))
        if accepted:
            states[(unit, count)] = receipt['best']['mean'][:2]
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == (
        'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5')
    spec = importlib.util.spec_from_file_location('dense_reference', helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    for row in rows:
        if row['accepted']:
            row['error_m'] = reference.distance_m(
                reference.latlon_from_enu(*states[(row['unit'], row['max_points'])]),
                reference.REFERENCE)
    result = dict(freeze_sha256=digest(freeze_path), evaluator_sha256=digest(__file__),
                  qualification='Three-scan development pilot plus one control; no holdout claim.',
                  rows=rows)
    with (HERE/'dense-v1-evaluation.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
