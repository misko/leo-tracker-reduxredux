"""Orbit-blind bounded refinement, equivalent to the earlier A/B prototype."""
import math

ALIAS_HZ = 1 / 4.4e-6


def circular(value):
    return (value + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def refine(score, frequency, epoch, iterations=3):
    if not math.isfinite(frequency) or not math.isfinite(epoch):
        raise ValueError('nonfinite refinement seed')
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError('iterations must be positive')
    trace, best, calls = [], None, 0
    for iteration in range(iterations):
        trials = []
        centers = [frequency + k * ALIAS_HZ for k in (-1, 0, 1)] if iteration == 0 else [frequency]
        offsets = [0.] if iteration == 0 else [-.5/iteration, -.25/iteration, 0., .25/iteration, .5/iteration]
        for center in centers:
            for offset in offsets:
                value = dict(score(center, epoch + offset))
                calls += 1
                if not all(math.isfinite(value[k]) for k in ('tracking_cfo_hz', 'margin', 'exact', 'control')):
                    continue
                if abs(circular(value['tracking_cfo_hz'] - center)) > 1000:
                    continue
                value.update(center_hz=center, epoch=epoch + offset)
                trials.append(value)
        if best is not None:
            trials.append(best)
        if not trials:
            return dict(status='no_local_maximum', trace=trace, calls=calls)
        best = max(trials, key=lambda r: r['margin'])
        trace.append(dict(best))
        frequency, epoch = best['tracking_cfo_hz'], best['epoch']
    return dict(status='refined', trace=trace, calls=calls, **best)


def winners(records):
    selected = {}
    for row in records:
        key = tuple(row['probe_key'])
        refinement = row['refinement']
        margin = refinement['margin'] if refinement['status'] == 'refined' else row['original_margin']
        priority = (margin, -row['row_index'])
        if key not in selected or priority > selected[key][0]:
            selected[key] = (priority, row['row_index'])
    return sorted(value[1] for value in selected.values())
