"""Same-model complete-state geometry/calibration/timing/q mode portfolio."""

import math
import time
from dataclasses import replace

import numpy as np


def starts(context, fixed, expanded):
    """Paired training-state seeds; no observed values, labels or references."""
    fv, fn = (np.asarray(fixed[k]).copy() for k in ('vector', 'nuisance'))
    ev, en = (np.asarray(expanded[k]).copy() for k in ('vector', 'nuisance'))
    c = context.model.clock_count
    if (fv.shape != ev.shape or fn.shape != en.shape
            or context.model.base_nuisance_count != c):
        raise ValueError('same shared-model frame and clock/q dimensions required')
    rows = [('expanded', ev.copy(), en.copy()), ('fixed-lift', fv.copy(), fn.copy())]
    for name, a, an, b, bn in (('fixed-geometry-calibration', fv, fn, ev, en),
                              ('expanded-geometry-calibration', ev, en, fv, fn)):
        v, n = b.copy(), bn.copy()
        v[:7], n[:c] = a[:7], an[:c]
        rows.append((name, v, n))
    v = ev.copy()
    v[:2] = 0.
    rows.append(('prior-center', v, en.copy()))
    for _, v, n in rows:
        if context.fixed_c:
            v[6] = 0.
        if not np.isfinite(v).all() or not np.isfinite(n).all():
            raise ValueError('complete finite paired source states required')
    return rows


class RecordingModel:
    def __init__(self, original):
        self.original_model = original
        self.calls, self.first_objective = 0, None

    def __getattr__(self, name):
        return getattr(self.original_model, name)

    def evaluate_joint(self, vector, nuisance):
        self.calls += 1
        result = self.original_model.evaluate_joint(vector, nuisance)
        if self.first_objective is None:
            self.first_objective = float(result[0])
        return result


def fit(context, fixed, expanded, incumbent, *, method='portfolio', max_evaluations=1000,
        max_seconds=120, refitter=None, auditor=None):
    if refitter is None or auditor is None:
        import common
        refitter = refitter or common.refit
        auditor = auditor or common.endpoint_status
    if (method not in ('portfolio', 'continuation') or type(max_evaluations) is not int
            or max_evaluations < 2 or not math.isfinite(max_seconds) or max_seconds <= 0):
        raise ValueError('explicit bounded portfolio or matched continuation required')
    begun = time.monotonic()
    deadline = min(begun+max_seconds, getattr(context, 'deadline', math.inf))
    iv, inn = (np.asarray(incumbent[k]).copy() for k in ('vector', 'nuisance'))
    audit = auditor(context, iv, inn)  # One counted source score, no hidden seed score.
    if not audit.get('feasible') or not math.isfinite(audit['training_objective']):
        raise ValueError('retained original expanded incumbent must be feasible')
    used, records = 1, []
    best = dict(vector=iv, nuisance=inn, objective=audit['training_objective'],
                origin='retained-own-arm-expanded-incumbent', accepted=audit['accepted'])
    inventory = starts(context, fixed, expanded)
    if method == 'continuation':
        inventory = inventory[:1]
    remaining_budget = max_evaluations-1
    quotas = [remaining_budget//len(inventory)+(i < remaining_budget % len(inventory))
              for i in range(len(inventory))]
    for i, ((label, v, n), quota) in enumerate(zip(inventory, quotas, strict=True)):
        remaining = deadline-time.monotonic()
        row = dict(origin=label, quota=quota, seed_vector=v.tolist(), seed_nuisance=n.tolist())
        if quota == 0 or remaining <= 0:
            records.append(dict(row, evaluations=0, reason='total-budget', accepted=False))
            continue
        recorded = RecordingModel(context.model)
        try:
            result = refitter(replace(context, model=recorded), v, n,
                max_evaluations=quota, max_seconds=remaining/(len(inventory)-i),
                fixed_c=context.fixed_c)
            diagnostic = result['diagnostics']
            if diagnostic['evaluations'] != recorded.calls or recorded.calls > quota:
                raise RuntimeError('exact shared refit call accounting failed')
            row.update(diagnostic)
            value = diagnostic['objective']
            if math.isfinite(value) and value < best['objective']:
                best = dict(vector=result['vector'], nuisance=result['nuisance'],
                    objective=value, origin=label, accepted=diagnostic['accepted'])
        except (ValueError, TimeoutError) as error:
            row.update(reason=f'{type(error).__name__}: {error}', accepted=False)
        used += recorded.calls
        row.update(evaluations=recorded.calls, initial_seed_objective=recorded.first_objective)
        records.append(row)
    return dict(vector=np.asarray(best['vector']).copy(),
        nuisance=np.asarray(best['nuisance']).copy(),
        diagnostics=dict(method=method, model='unchanged shared conditional Gaussian',
            selection='minimum total training objective including retained own-arm incumbent',
            evaluations=used, maximum_evaluations=max_evaluations,
            elapsed_seconds=time.monotonic()-begun,
            objective=best['objective'], accepted=best['accepted'], selected_origin=best['origin'],
            incumbent_audit=audit, records=records,
            seed_policy='same fitted-c five complete starts; c=0 changes only coefficient6',
            station_or_window_inputs=False))
