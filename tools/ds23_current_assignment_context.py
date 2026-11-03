"""Bind diagnostics to current labels while preserving observation ordering."""

import numpy as np


def current_base_context(data, current):
    old = data['base']
    if ([r['component'] for r in old.rows] != [r['component'] for r in current.rows]
            or old.members != current.members
            or [(s.start, s.stop) for s in old.slices] != [(s.start, s.stop) for s in current.slices]
            or not np.array_equal(current.keep, data['keep'])):
        raise ValueError('current assignment must preserve measurement layout and mask')
    expected = [(r['component'], r['candidate_index'], r['candidate_norad']) for r in data['node']['seed']['rows']]
    actual = [(r['component'], r['candidate_index'], r['candidate_norad']) for r in current.rows]
    if actual != expected:
        raise ValueError('diagnostic base must match current assignment labels')
    return dict(data, base=current)
