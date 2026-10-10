"""Bounded full-support scalar envelope refinement; no recording ports."""
import importlib.util
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

SOURCE = Path(__file__).resolve().parents[1] / '2026_10_10_position_error_iter156/envelopes.py'
SPEC = importlib.util.spec_from_file_location('envelopes156_for157', SOURCE)
ENVELOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENVELOPE)


def log_gap(lower, upper):
    """Log absolute integral gap, avoiding subtraction of tiny/huge integrals."""
    if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
        raise ValueError('invalid finite log bounds')
    return -math.inf if lower == upper else upper + math.log(-math.expm1(lower-upper))


def integrate(callback, lower, upper, *, h_bound, u_bound, seam_bound,
              target_log_width=1e-4, maximum_calls=512):
    """callback(center)->(log integrand, derivative); seam_bound(left,right)->logJ.

    All bounds/intervals are fixed by the caller's declared model. No samples are
    discarded from cost accounting. A failed child leaves its parent's envelope
    active, preserving full support while explicitly failing this attempt.
    """
    if (not all(math.isfinite(x) for x in (lower, upper, h_bound, u_bound, target_log_width))
            or lower >= upper or not math.isfinite(upper-lower)
            or h_bound < 0 or u_bound < -h_bound or target_log_width <= 0
            or isinstance(maximum_calls, bool) or not isinstance(maximum_calls, int)
            or not 1 <= maximum_calls <= 512):
        raise ValueError('invalid declared support/bounds/budget')
    ledger, active, splits = [], [], []
    calls = 0

    def evaluate(left, right, parent):
        nonlocal calls
        center = left + (right-left)/2
        row = dict(id=len(ledger), parent=parent, lower=left, upper=right,
                   center=center, called=False, status='failed')
        ledger.append(row)
        try:
            if calls >= maximum_calls:
                raise ValueError('value-gradient call budget exceeded')
            calls += 1
            row['called'] = True
            value, gradient = callback(center)
            if not math.isfinite(value) or not math.isfinite(gradient):
                raise ValueError('nonfinite callback result')
            row.update(value=float(value), gradient=float(gradient))
            jump = seam_bound(left, right)
            envelope = ENVELOPE.cell_envelope(value, gradient, (right-left)/2,
                h_bound, u_bound, seam_log_total=jump)
            row.update(status='complete', envelope=envelope,
                       log_absolute_gap=log_gap(envelope['log_lower'], envelope['log_upper']))
        except Exception as error:
            row['error'] = repr(error)
        return row

    root = evaluate(lower, upper, None)
    if root['status'] == 'complete':
        active.append(root['id'])
    status = 'callback_failed' if not active else None
    while status is None:
        low = float(logsumexp([ledger[i]['envelope']['log_lower'] for i in active]))
        high = float(logsumexp([ledger[i]['envelope']['log_upper'] for i in active]))
        if not math.isfinite(low) or not math.isfinite(high) or low > high:
            status = 'numerical_bounds_failed'
            break
        if high-low <= target_log_width:
            status = 'target_met'
            break
        if calls+2 > maximum_calls:
            status = 'budget_exhausted'
            break
        chosen = min(active, key=lambda i: (-ledger[i]['log_absolute_gap'], ledger[i]['lower'], i))
        parent = ledger[chosen]
        midpoint = parent['center']
        if not parent['lower'] < midpoint < parent['upper']:
            status = 'partition_resolution_exhausted'
            break
        left = evaluate(parent['lower'], midpoint, chosen)
        if left['status'] != 'complete':
            splits.append(dict(parent=chosen, children=[left['id']], accepted=False))
            status = 'callback_failed'
            break
        right = evaluate(midpoint, parent['upper'], chosen)
        accepted = right['status'] == 'complete'
        splits.append(dict(parent=chosen, children=[left['id'], right['id']], accepted=accepted))
        if not accepted:
            status = 'callback_failed'
            break
        active.remove(chosen)
        active.extend([left['id'], right['id']])
    partition = [ledger[i] for i in sorted(active, key=lambda i: ledger[i]['lower'])]
    coverage = bool(partition and partition[0]['lower'] == lower and partition[-1]['upper'] == upper
                    and all(a['upper'] == b['lower'] for a, b in zip(partition, partition[1:])))
    bounds = None
    if coverage:
        low = float(logsumexp([row['envelope']['log_lower'] for row in partition]))
        high = float(logsumexp([row['envelope']['log_upper'] for row in partition]))
        bounds = dict(log_lower=low, log_upper=high, log_width=high-low)
    return dict(status=status, target_met=status == 'target_met', full_support_covered=coverage,
                support=[lower,upper], bounds=bounds, actual_calls=calls,
                maximum_calls=maximum_calls, target_log_width=target_log_width,
                active_partition_ids=[row['id'] for row in partition], ledger=ledger, splits=splits,
                scope='Conservative numerical envelope, not rigorous floating-point certification')
