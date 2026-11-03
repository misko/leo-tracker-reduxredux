"""Fixed-width continuation schedule; every selectable final score uses sigma125."""

import math
import time
from dataclasses import replace

import numpy as np
from leo.analysis.shared_scan_model import SharedScanObjective


class WidthModel(SharedScanObjective):
    def __init__(self, source, sigma):
        if type(source) is not SharedScanObjective or sigma not in (125, 250, 500, 1000):
            raise ValueError('exact shared source and one declared fixed width required')
        self.__dict__.update(source.__dict__)
        self.fixed_width_hz = float(sigma)

    def hyperparameters(self, tail):
        values = super().hyperparameters(tail)
        if self.fixed_width_hz == 125:
            return values
        return (np.full_like(values[0], self.fixed_width_hz), *values[1:])


class Recorded:
    def __init__(self, model):
        self.model, self.calls, self.initial_objective = model, 0, None

    def __getattr__(self, name):
        return getattr(self.model, name)

    def evaluate_joint(self, vector, nuisance):
        self.calls += 1
        result = self.model.evaluate_joint(vector, nuisance)
        if self.initial_objective is None:
            self.initial_objective = float(result[0])
        return result


def fit(context, seed, incumbent, *, anneal=True, max_evaluations=1000, max_seconds=120,
        refitter=None, auditor=None):
    if refitter is None or auditor is None:
        import common
        refitter, auditor = refitter or common.refit, auditor or common.endpoint_status
    if (max_evaluations != 1000 or not math.isfinite(max_seconds) or not 0 < max_seconds <= 120
            or type(anneal) is not bool):
        raise ValueError('declared1000-call/<=120-second annealing or matched control required')
    begun = time.monotonic()
    deadline = min(begun+max_seconds, getattr(context, 'deadline', math.inf))
    iv, inn = (np.asarray(incumbent[k]).copy() for k in ('vector', 'nuisance'))
    audit = auditor(context, iv, inn)
    if not audit.get('feasible'):
        raise ValueError('raw own-arm125 incumbent must be feasible')
    best = dict(vector=iv, nuisance=inn, objective=audit['training_objective'],
                accepted=audit['accepted'], origin='raw-own-arm125-incumbent')
    v, n = (np.asarray(seed[k]).copy() for k in ('vector', 'nuisance'))
    if context.fixed_c:
        v[6] = 0.
    schedule = [(1000, 149), (500, 150), (250, 150), (125, 550)] if anneal else [(125, 999)]
    records, calls = [], 1
    for index, (width, quota) in enumerate(schedule):
        remaining = deadline-time.monotonic()
        row = dict(sigma_hz=width, quota=quota, seed_vector=v.tolist(), seed_nuisance=n.tolist())
        if remaining <= 0:
            records.append(dict(row, evaluations=0, reason='whole-deadline', accepted=False))
            continue
        model = Recorded(WidthModel(context.model, width))
        try:
            seconds = remaining*quota/sum(q for _, q in schedule[index:])
            result = refitter(replace(context, model=model), v, n, max_evaluations=quota,
                             max_seconds=seconds, fixed_c=context.fixed_c)
            d = result['diagnostics']
            if model.calls != d['evaluations'] or model.calls > quota:
                raise RuntimeError('exact stage objective accounting failed')
            row.update(d)
            v, n = np.asarray(result['vector']).copy(), np.asarray(result['nuisance']).copy()
            # Broader widths are only a path through parameter space. Their
            # objectives are never ranked against125 or each other to select.
            if width == 125 and d['objective'] < best['objective']:
                best = dict(vector=v.copy(), nuisance=n.copy(), objective=d['objective'],
                            accepted=d['accepted'], origin='final125-stage')
        except (ValueError, TimeoutError) as error:
            row.update(reason=f'{type(error).__name__}: {error}', accepted=False)
        calls += model.calls
        row.update(evaluations=model.calls, initial_stage_objective=model.initial_objective,
                   final_vector=v.tolist(), final_nuisance=n.tolist(),
                   selectable_final_target=width == 125)
        records.append(row)
    return dict(vector=best['vector'], nuisance=best['nuisance'], diagnostics=dict(
        method='fixed-width-annealing' if anneal else 'matched125-continuation',
        evaluations=calls, maximum_evaluations=1000, elapsed_seconds=time.monotonic()-begun,
        objective=best['objective'], accepted=best['accepted'], selected_origin=best['origin'],
        final_target_sigma_hz=125, incumbent_audit=audit, stages=records,
        fixed_c=context.fixed_c,
        priors='unchanged common/relative timing, clock, fixed contrast and q',
        selection='original125 total training objective ONLY; broad scores are stage diagnostics'))
