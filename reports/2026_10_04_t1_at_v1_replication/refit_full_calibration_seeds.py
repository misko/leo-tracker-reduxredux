"""Full-data prefit continuation from better archived nuisance initializations.

Use the same full top-window observations, bootstrap bank and priors at the
known roof. Two equally budgeted starts per RF arm: the saved full prefit and
the lowest-scoring archived initialization. No train/eval split. This does NOT
yet rebuild the nonlinear RX correction, associations or position solution.
"""
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from full_calibration_seed_audit import seed_vector
from full_scan_cohort import HERE, OUT as COHORT, SCANS, ARMS, digest, serial
from full_data_calibration import FullCalibration, INPUTS
from rf_calibration_diagnostic import CalibrationObjective
from convergence_fisher import fit

OUT = COHORT/'calibration-seed-audit/refits'
BUDGET = dict(start_s=15., polish_s=20.)


def fixed_stationarity(obj, record):
    """Nuisance KKT: fixed roof coordinates are not optimization variables."""
    from constrained_fit import kkt_residual
    assert record['fixed_location']
    vector = np.asarray(record['vector']); scale = np.asarray(obj.scale).copy(); scale[:2] = 1.
    z = vector/scale; z[:2] = record['point_km']
    value, gradient = obj.evaluate(vector)
    gradient = gradient*scale; gradient[:2] = 0.
    bounds = [(None if lo is None else lo/s, None if hi is None else hi/s)
              for (lo, hi), s in zip(obj.bounds, scale)]
    bounds[:2] = [(x, x) for x in z[:2]]
    matrix = np.zeros((len(obj.base.satellites), len(vector)))
    matrix[:, 6] = 1.; matrix[:, 7:obj.size] = obj.base.basis; matrix *= scale
    lower = np.full(len(matrix), obj.base.minimum_shift_s+1e-6)
    upper = np.full(len(matrix), obj.base.maximum_shift_s-1e-6)
    return float(value), float(kkt_residual(gradient, z, bounds, matrix, lower, upper))


def run(task):
    scan, arm = task
    target = OUT/f'{scan}-{arm}.json'
    if target.exists(): return str(target)
    seed_report_path = OUT.parent/'audit.json'
    seed_report = json.loads(seed_report_path.read_text())
    summary = next(r for r in seed_report['summaries'] if (r['scan'], r['arm']) == (scan, arm))
    for path, sha in seed_report['sources'][scan].items(): assert digest(Path(path)) == sha
    cal = FullCalibration(scan); data = cal.data; ids = np.asarray(cal.record['satellite_indices'])
    baseline = cal.record['pre'][arm]
    name = summary['best_seed']
    if name.startswith('fold-'):
        path = INPUTS/scan/'seed-timing-v6/calibration-v2'/f'fold-{name.split("-")[1]}.json'
        candidate = json.loads(path.read_text())['arms'][arm]
    elif name == 'full-prefit': candidate = baseline
    else: raise ValueError('Unexpected unoptimized bootstrap winner; handle its zero RF initialization explicitly')
    obj = CalibrationObjective(data, data.initial, ids, False, 60.)
    obj.center = cal.record['rf_center_hz']; obj.features = ((data.rf-obj.center)/1e9)[:, None]
    obj.likelihood.features = obj.features
    obj.base.minimum_shift_s = max(obj.base.minimum_shift_s, -20.)
    obj.base.maximum_shift_s = min(obj.base.maximum_shift_s, 20.)
    if arm == 'zero-c': obj.bounds[-1] = (0., 0.)
    records = []
    for label, seed in [('current-full-prefit', baseline), ('best-archived-seed', candidate)]:
        start = seed_vector(obj, seed['parameters'], ids, seed['coefficient'])
        r = fit(obj, start, [0., 0.], BUDGET['start_s'], True, radius_km=4.)
        r['stage'] = label; records.append(r)
    best = min(records, key=lambda r: r['objective'])
    r = fit(obj, np.asarray(best['vector']), [0., 0.], BUDGET['polish_s'], True, radius_km=4.)
    r['stage'] = 'polish'; records.append(r)
    best = min(records, key=lambda r: r['objective'])
    value, kkt = fixed_stationarity(obj, best)
    np.testing.assert_allclose(value, best['objective'], atol=1e-7, rtol=0)
    assert value <= baseline['objective']+1e-7
    assert max(abs(np.asarray(best['parameters'])[6+ids])) <= 20.+1e-7
    old_timing = np.asarray(baseline['parameters'])[6+ids]
    new_timing = np.asarray(best['parameters'])[6+ids]
    result = dict(scope=__doc__, scan=scan, arm=arm, selected_seed=name,
        input_sources=cal.sources, seed_audit_sha256=digest(seed_report_path),
        implementation_sha256=digest(Path(__file__)), maximum_budgets_s=BUDGET,
        fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
        heldout_original_rows=[], seed_numbers=data.numbers[ids],
        old_prefit_objective=baseline['objective'], objective=value,
        score_change=value-baseline['objective'], kkt=kkt, converged=bool(kkt <= 1e-3),
        receiver_parameter_changes=(np.asarray(best['parameters'])[2:6]-np.asarray(baseline['parameters'])[2:6]),
        timing_change_rms_s=float(np.sqrt(np.mean((new_timing-old_timing)**2))),
        best=best, records=records)
    target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
    print('CALIBRATION RESTART', scan, arm, name, 'NLL change', round(result['score_change'], 2),
          'converged', result['converged'], flush=True)
    return str(target)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run, (s, a)) for s in SCANS for a in ARMS]): f.result()
    rows = [json.loads((OUT/f'{s}-{a}.json').read_text()) for s in SCANS for a in ARMS]
    # A former reporting helper audited free position coordinates too. Preserve
    # its raw result; reconstruct fixed-roof convergence in a separate receipt.
    for r in rows:
        cal = FullCalibration(r['scan']); data = cal.data
        ids = np.asarray(cal.record['satellite_indices'])
        obj = CalibrationObjective(data, data.initial, ids, False, 60.)
        obj.center = cal.record['rf_center_hz']; obj.features = ((data.rf-obj.center)/1e9)[:, None]
        obj.likelihood.features = obj.features; obj.base.deadline = float('inf')
        obj.base.minimum_shift_s = max(obj.base.minimum_shift_s, -20.)
        obj.base.maximum_shift_s = min(obj.base.maximum_shift_s, 20.)
        if r['arm'] == 'zero-c': obj.bounds[-1] = (0., 0.)
        value, kkt = fixed_stationarity(obj, r['best'])
        np.testing.assert_allclose(value, r['objective'], atol=1e-7, rtol=0)
        np.testing.assert_allclose(kkt, r['best']['kkt_residual'], atol=1e-7, rtol=0)
        r.update(kkt=kkt, converged=bool(kkt <= 1e-3))
    report = dict(scope=__doc__, cases=len(rows), converged=sum(r['converged'] for r in rows),
                  summaries=[{k: r[k] for k in ('scan', 'arm', 'selected_seed', 'score_change', 'converged',
                                               'receiver_parameter_changes', 'timing_change_rms_s')} for r in rows],
                  downstream_not_rerun=True, fixed_roof_kkt_reconstructed=True,
                  audit_implementation_sha256=digest(Path(__file__)),
                  reporting_note='This fixed-roof audit supersedes the free-position KKT fields in the original per-case receipts.')
    (OUT/'summary.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2))
