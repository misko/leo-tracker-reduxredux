"""Post-hoc satellite influence audit; does not tune the frozen benchmark.

Delete one fitted-c association's windows and its bank satellite, then refit
both RF arms on identical retained observations. Scores across different
deletions are NOT comparable. Position change and within-deletion best-minus-
roof score are reported. Short-budget fits are screening diagnostics, not
certified minima or causal evidence of incorrect identity.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
import json
from pathlib import Path
import time

import numpy as np

from cohort import digest
from numeric_data import view
from position_search import prepare
from fisher_position import fit
from track_diagnostics import residual_statistics
from satellite_gradients import components
from position_direct import coordinate_jacobian

ARMS = ('fitted-c', 'zero-c')
LABELS = ['A', 'B', *[f'N{i:02d}' for i in range(1, 17)]]


def delete_satellite(data, owners, number):
    """Owners are frozen fitted-c labels, identical in both RF arms."""
    keep = np.ones(len(owners), bool) if number is None else owners != number
    ids = np.flatnonzero(np.ones(len(data.numbers), bool) if number is None else data.numbers != number)
    if not np.any(keep) or not len(ids):
        raise ValueError('deletion leaves no evidence or satellite bank')
    reduced = view(data, keep)
    for key in ('numbers', 'position', 'velocity'):
        setattr(reduced, key, getattr(data, key)[ids].copy())
    reduced.initial = np.r_[data.initial[:6], data.initial[6:][ids]]
    return reduced, keep, ids


def remap_start(objective, record, ids, arm):
    """Preserve remaining satellites' total shifts under a new zero-sum basis."""
    params = np.asarray(record['parameters'])
    total = params[6:][ids]
    common = float(np.mean(total))
    # The optimizer enforces the same total-shift bounds and common box.
    # Recenter without changing total shifts unless common is infeasible.
    common_clipped = np.clip(common, -10., 10.)
    return np.r_[params[:6], common_clipped,
                 objective.base.basis.T @ (total - common),
                 record['coefficient'] if arm == 'fitted-c' else 0.]


def make_objective(data, full_rf_center, arm):
    from rf_calibration_diagnostic import CalibrationObjective
    obj = CalibrationObjective(data, data.initial, np.arange(len(data.numbers)), False, 8.)
    obj.base.minimum_shift_s = max(obj.base.minimum_shift_s, -20.)
    obj.base.maximum_shift_s = min(obj.base.maximum_shift_s, 20.)
    # Keep the original RF reference when deletion removes a whole channel.
    obj.center = full_rf_center
    obj.features = ((data.rf - full_rf_center) / 1e9)[:, None]
    obj.likelihood.features = obj.features
    if arm == 'zero-c':
        obj.bounds[-1] = (0., 0.)
    return obj


@lru_cache(maxsize=2)
def load_case(root, label):
    directory = Path(root) / label / 'seed-timing-v6'
    data, meta = prepare(directory, 'alternatives', 'support', 1., permit_calibration_warning=True)
    namespace = 'position-fisher-v2-calibration-warning' if meta.get('calibration_warnings') else 'position-fisher-v2'
    source = directory / namespace / 'selection-p10-g600-t1/alternatives-support-100/summary.json'
    saved = json.loads(source.read_text())
    if saved['signature']['inputs'] != meta:
        raise ValueError('baseline position input mismatch')
    selection = json.loads((directory / 'selection-p10-g600-t1.json').read_text())
    assignments = selection['arms']['fitted-c']['alternatives']['final']['assignments']
    # prepare() sorts row_index; it does not relabel based on posterior winners.
    owners = np.array([a['catalog_number'] for a in sorted(assignments, key=lambda a: a['row_index'])])
    if len(owners) != len(data.times) or len(np.unique(data.group)) != len(data.times):
        raise ValueError('expected exactly one frozen assigned candidate per window')
    mean = float(np.mean(data.initial[6:]))
    data.initial[6:] *= min(1., (10-1e-6)/max(abs(mean), 10-1e-6))
    data.initial[6:] = np.clip(data.initial[6:], -20+1e-6, 20-1e-6)
    return data, meta, owners, saved, str(source), digest(source.read_bytes())


def roof_diagnostics(data, owners, saved):
    center = float(np.mean(np.unique(data.rf)))
    rows = []
    for arm in ARMS:
        obj = make_objective(data, center, arm)
        record = saved['arms'][arm]['roof']
        vector = np.asarray(record['vector'])
        obj.base.deadline = float('inf')
        value, _ = obj.evaluate(vector)
        if abs(value-record['objective']) > 1e-6:
            raise ValueError('saved roof objective reconstruction failed')
        predicted, visible, jac = obj.base.predict(vector[:obj.size], with_jacobian=True)
        predicted += (obj.features @ vector[obj.size:])[:, None]
        alias = obj.likelihood.alias_hz
        residual = (data.measured[:, None]-predicted+alias/2) % alias-alias/2
        like = obj.likelihood.last_result
        parts = components(jac, like['prediction_gradient'], like['row_association_probability'],
                           data.receiver, data.numbers, coordinate_jacobian([0., 0.]))
        for j, number in enumerate(data.numbers):
            use = owners == number
            if not np.any(use):
                continue
            per_rx = []
            for rx in (0, 1):
                mask = use & (data.receiver == rx)
                if not np.any(mask):
                    continue
                stats = residual_statistics(data.times[mask], residual[mask, j], data.channel[mask])
                if stats is not None:
                    per_rx.append(dict(receiver=rx, windows=int(mask.sum()), **stats))
            stats = residual_statistics(data.times[use], residual[use, j], data.receiver[use]*10+data.channel[use])
            gradient = np.sum([[p['east_per_100m'], p['north_per_100m']]
                               for p in parts if p['catalog_number'] == number], axis=0)
            rows.append(dict(arm=arm, satellite=int(number), windows=int(use.sum()),
                rx0_windows=int(np.sum(use & (data.receiver == 0))),
                rx1_windows=int(np.sum(use & (data.receiver == 1))),
                span_s=float(np.ptp(data.times[use])), stats=stats, per_rx=per_rx,
                east_per_100m=float(gradient[0]), north_per_100m=float(gradient[1]),
                gradient_strength_per_100m=float(np.linalg.norm(gradient)),
                visible_fraction=float(np.mean(visible[use, j])),
                effective_soft_support=float(like['row_association_probability'][:, j].sum())))
    return rows


def run_one(task):
    root, output, label, number, budget, phase = task
    path = Path(output) / phase / label / ('baseline.json' if number is None else f'drop-{number}.json')
    data, meta, owners, saved, source, source_hash = load_case(root, label)
    signature = dict(source=source, source_sha256=source_hash, label=label, satellite=number,
                     budget_s=budget, implementation=digest(Path(__file__).read_bytes()),
                     deletion='remove owned windows and bank satellite; no reassignment',
                     rf_reference_hz=float(np.mean(np.unique(data.rf))))
    if path.exists():
        previous = json.loads(path.read_text())
        if previous['signature'] != signature:
            raise ValueError('influence audit cache mismatch')
        return str(path)
    reduced, keep, ids = delete_satellite(data, owners, number)
    outcomes = {}
    for arm in ARMS:
        obj = make_objective(reduced, signature['rf_reference_hz'], arm)
        old = saved['arms'][arm]
        starts = [old['roof'], old['best_found']]
        if phase == 'confirm':
            previous_path = Path(output) / 'screen' / label / path.name
            if previous_path.exists():
                previous = json.loads(previous_path.read_text())['arms'][arm]
                # Screen vectors already have the reduced bank: do not remap twice.
                start_roof = np.asarray(previous['roof']['vector'])
                start_best = np.asarray(previous['best']['vector'])
                best_point = previous['best']['point_km']
            else:
                raise ValueError('confirmation requires completed paired screening result')
        else:
            start_roof = remap_start(obj, starts[0], ids, arm)
            start_best = remap_start(obj, starts[1], ids, arm)
            best_point = starts[1]['point_km']
        roof = fit(obj, start_roof, [0., 0.], budget/4, True)
        near = fit(obj, roof['vector'], [0., 0.], budget*3/8, False)
        far = fit(obj, start_best, best_point, budget*3/8, False)
        best = min([near, far], key=lambda r: r['objective'])
        # Baseline must not lose an already better saved solution.
        if number is None and old['best_found']['objective'] < best['objective']:
            best = old['best_found']
        radius = float(np.linalg.norm(best['point_km'])*1000)
        outcomes[arm] = dict(roof=roof, starts=[near, far], best=best,
            radius_m=radius, boundary=radius>=1999.,
            converged_joint=bool(best['success'] and not best['fixed_location']),
            best_minus_roof_nll=float(best['objective']-roof['objective']),
            calibration_warning=bool(meta.get('calibration_warnings')))
    result = dict(signature=signature, original_windows=len(keep), retained_windows=int(keep.sum()),
                  removed_windows=int((~keep).sum()), arms=outcomes)
    if number is None:
        result['roof_satellite_diagnostics'] = roof_diagnostics(data, owners, saved)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(result, stream, allow_nan=False)
    return str(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root'); p.add_argument('output')
    p.add_argument('--labels', nargs='+', default=LABELS)
    p.add_argument('--workers', type=int, default=12)
    p.add_argument('--budget', type=float, default=8.)
    p.add_argument('--phase', choices=['screen', 'confirm'], default='screen')
    p.add_argument('--tasks-json', type=Path)
    a = p.parse_args()
    if not 0 < a.budget <= 120 or not 1 <= a.workers <= 14:
        raise ValueError('bounded budget/workers required')
    if a.tasks_json:
        pairs = json.loads(a.tasks_json.read_text())
    else:
        pairs = []
        for label in a.labels:
            selection = json.loads((Path(a.root)/label/'seed-timing-v6/selection-p10-g600-t1.json').read_text())
            numbers = sorted({r['catalog_number'] for r in selection['arms']['fitted-c']['alternatives']['final']['assignments']})
            pairs.extend((label, n) for n in [None, *numbers])
        # Baselines and the clearest converged boundary case run first.
        pairs.sort(key=lambda pair: (pair[1] is not None, pair[0] != 'N15', LABELS.index(pair[0])))
    tasks = [(a.root, a.output, label, n, a.budget, a.phase) for label, n in pairs]
    start = time.monotonic()
    failures = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(run_one, task): task for task in tasks}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                path = future.result()
                print(i, '/', len(tasks), path, 'elapsed', round(time.monotonic()-start, 1), flush=True)
            except Exception as error:
                task = futures[future]
                failures.append(dict(label=task[2], satellite=task[3], error=repr(error)))
                print('FAILED', failures[-1], flush=True)
    if failures:
        raise RuntimeError(f'{len(failures)} audit tasks failed: {failures[:5]}')


if __name__ == '__main__':
    main()
