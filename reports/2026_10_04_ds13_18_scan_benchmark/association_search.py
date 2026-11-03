"""Pure greedy and one-out/many-in search with exclusive WINDOW accounting.

An observation row is one candidate hypothesis. Alternatives from the same
receiver/channel/probe share a group; selecting one locks the entire group.
Several satellites can remain active simultaneously in different groups.
"""
from dataclasses import dataclass
import math
import time

import numpy as np


@dataclass(frozen=True)
class Settings:
    penalty: float = 10.
    tolerance_hz: float = 600.
    minimum_windows: int = 10
    minimum_span_s: float = 5.
    maximum_gap_s: float = 5.
    residual_sigma_hz: float = 200.
    timing_sigma_s: float = 1.

    def __post_init__(self):
        if self.penalty < 0 or not math.isfinite(self.penalty):
            raise ValueError('penalty must be finite and nonnegative')
        if type(self.minimum_windows) is not int or self.minimum_windows < 1:
            raise ValueError('minimum_windows must be a positive integer')
        if self.minimum_span_s < 0 or not math.isfinite(self.minimum_span_s):
            raise ValueError('minimum_span_s must be finite and nonnegative')
        for name in ('tolerance_hz', 'maximum_gap_s', 'residual_sigma_hz', 'timing_sigma_s'):
            value = getattr(self, name)
            if value <= 0 or not math.isfinite(value):
                raise ValueError(f'{name} must be finite and positive')


def compile_mode(record, receiver, channel):
    rows = np.asarray(record['eligible_rows'], dtype=int)
    errors = np.asarray(record['residual_hz'], dtype=float)
    if rows.ndim != 1 or errors.shape != rows.shape or len(np.unique(rows)) != len(rows):
        raise ValueError('invalid or duplicate mode rows')
    if np.any(rows < 0) or np.any(rows >= len(receiver)) or not np.all(np.isfinite(errors)):
        raise ValueError('invalid mode row range or residual')
    if not math.isfinite(record['offset_s']):
        raise ValueError('nonfinite satellite timing')
    lanes = []
    for rx, ch in sorted(set(zip(receiver[rows], channel[rows]))):
        use = np.flatnonzero((receiver[rows] == rx) & (channel[rows] == ch))
        # Stable residual + original-row tie break, independent of input ordering.
        use = use[np.lexsort((rows[use], abs(errors[use])))]
        lanes.append((rows[use], errors[use]))
    return dict(catalog_number=int(record['catalog_number']), offset_s=float(record['offset_s']),
                rows=rows, lanes=lanes)


class Search:
    def __init__(self, records, groups, times, receiver, channel, *, settings=Settings(), allowed=None):
        self.settings = settings
        groups = np.asarray(groups)
        self.times = np.asarray(times, dtype=float)
        receiver, channel = np.asarray(receiver), np.asarray(channel)
        if groups.ndim != 1 or not len(groups) or any(x.shape != groups.shape for x in (self.times, receiver, channel)):
            raise ValueError('misaligned observations')
        if not np.all(np.isfinite(self.times)):
            raise ValueError('nonfinite time')
        self.group_ids, self.groups = np.unique(groups, return_inverse=True)
        for group in range(len(self.group_ids)):
            rows = np.flatnonzero(self.groups == group)
            if len(np.unique(receiver[rows])) != 1 or len(np.unique(channel[rows])) != 1:
                raise ValueError('one window cannot span receiver/channel lanes')
        self.allowed = np.ones(len(groups), bool) if allowed is None else np.asarray(allowed, bool)
        if self.allowed.shape != groups.shape:
            raise ValueError('allowed mask mismatch')
        self.modes = [compile_mode(r, receiver, channel) for r in records]
        self.group_modes = [set() for _ in self.group_ids]
        self.catalog_modes = {}
        for index, mode in enumerate(self.modes):
            self.catalog_modes.setdefault(mode['catalog_number'], set()).add(index)
            for group in np.unique(self.groups[mode['rows']]):
                self.group_modes[group].add(index)

    def evaluate(self, index, used):
        s, mode = self.settings, self.modes[index]
        chosen, residuals = [], []
        for rows, errors in mode['lanes']:
            eligible = np.flatnonzero((abs(errors) <= s.tolerance_hz) & self.allowed[rows] & ~used[self.groups[rows]])
            _, first = np.unique(self.groups[rows[eligible]], return_index=True)
            eligible = eligible[first]
            eligible = eligible[np.argsort(self.times[rows[eligible]], kind='stable')]
            for part in np.split(eligible, np.flatnonzero(np.diff(self.times[rows[eligible]]) > s.maximum_gap_s)+1):
                if len(part) >= s.minimum_windows and self.times[rows[part[-1]]] - self.times[rows[part[0]]] >= s.minimum_span_s:
                    chosen.extend(rows[part].tolist())
                    residuals.extend(errors[part].tolist())
        count = len(chosen)
        sse = float(np.dot(residuals, residuals))
        return dict(count=count, rows=chosen, errors=residuals,
                    tie_score=-.5*sse/s.residual_sigma_hz**2-.5*(mode['offset_s']/s.timing_sigma_s)**2,
                    rms_hz=math.sqrt(sse/count) if count else None)

    def objective(self, chosen):
        return sum(r['count'] for r in chosen.values()) - self.settings.penalty*len(chosen)

    def affected(self, rows):
        return set().union(*(self.group_modes[g] for g in np.unique(self.groups[rows]))) if len(rows) else set()

    def refresh(self, indices, chosen, used, cache, forbidden=frozenset()):
        for index in indices:
            number = self.modes[index]['catalog_number']
            if number not in chosen and number not in forbidden:
                cache[index] = self.evaluate(index, used)

    def fill(self, chosen, used, cache, forbidden=frozenset()):
        trace = []
        while True:
            candidates = [i for i, m in enumerate(self.modes)
                          if m['catalog_number'] not in chosen and m['catalog_number'] not in forbidden
                          and cache[i]['count'] > self.settings.penalty]
            if not candidates:
                return trace
            index = max(candidates, key=lambda i:(cache[i]['count'], cache[i]['tie_score'], -self.modes[i]['catalog_number'], -i))
            number = self.modes[index]['catalog_number']
            value = dict(cache[index], mode_index=index, catalog_number=number)
            groups = self.groups[value['rows']]
            if len(np.unique(groups)) != len(groups) or np.any(used[groups]):
                raise AssertionError('attempted double-counting of a GLRT window')
            chosen[number] = value
            used[groups] = True
            trace.append(dict(catalog_number=number, mode_index=index, added_windows=value['count'],
                              marginal_score=value['count']-self.settings.penalty, objective=self.objective(chosen)))
            self.refresh(self.affected(value['rows']), chosen, used, cache, forbidden)

    def export(self, chosen):
        assignments, selected = [], []
        for number, value in chosen.items():
            mode = self.modes[value['mode_index']]
            assignments.extend(dict(row_index=int(row), group_index=int(self.groups[row]), catalog_number=number,
                                    mode_index=value['mode_index'], residual_hz=float(error))
                               for row, error in zip(value['rows'], value['errors']))
            selected.append(dict(catalog_number=number, mode_index=value['mode_index'], offset_s=mode['offset_s'],
                                 count=value['count'], rms_hz=value['rms_hz']))
        if len(assignments) != len({r['group_index'] for r in assignments}):
            raise AssertionError('duplicate assigned windows')
        return dict(assigned=len(assignments), unassigned=len(self.group_ids)-len(assignments),
                    denominator=len(self.group_ids), coverage=len(assignments)/len(self.group_ids),
                    satellites=len(selected), objective=self.objective(chosen), assignments=assignments, selected=selected)

    def run(self, maximum_passes=3):
        if type(maximum_passes) is not int or maximum_passes < 0:
            raise ValueError('maximum_passes must be nonnegative integer')
        start = time.monotonic()
        used = np.zeros(len(self.group_ids), bool)
        chosen = {}
        cache = [self.evaluate(i, used) for i in range(len(self.modes))]
        trace = self.fill(chosen, used, cache)
        initial = self.export(chosen)
        trials, passes, converged = [], [], False
        for sweep in range(maximum_passes):
            accepted = 0
            for number in list(chosen):
                if number not in chosen:
                    continue
                removed = chosen[number]
                before = self.objective(chosen)
                trial = {n:v for n,v in chosen.items() if n != number}
                tu, tc = used.copy(), cache.copy()
                tu[self.groups[removed['rows']]] = False
                self.refresh(self.affected(removed['rows']), trial, tu, tc, {number})
                additions = self.fill(trial, tu, tc, {number})
                score = self.objective(trial)
                record = dict(pass_index=sweep+1, removed=number, before_score=before, trial_score=score,
                              replacement_satellites=[r['catalog_number'] for r in additions], accepted=score > before)
                if record['accepted']:
                    self.refresh(self.catalog_modes[number], trial, tu, tc)
                    extra = self.fill(trial, tu, tc)
                    record.update(refill=[r['catalog_number'] for r in extra], after_score=self.objective(trial))
                    chosen, used, cache = trial, tu, tc
                    accepted += 1
                trials.append(record)
            passes.append(dict(pass_index=sweep+1, accepted=accepted, objective=self.objective(chosen)))
            if not accepted:
                converged = True
                break
        return dict(initial=initial, final=self.export(chosen), greedy_trace=trace, trials=trials, passes=passes,
                    converged=converged, termination='greedy_only' if maximum_passes == 0 else ('no_improving_greedy_repair' if converged else 'pass_limit'),
                    elapsed_s=time.monotonic()-start,
                    scope='Window-exclusive greedy then one-out/greedy-many-in; not an exact combinatorial optimum or identity certification.')
