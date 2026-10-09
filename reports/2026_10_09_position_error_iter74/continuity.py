"""Descriptive posterior identity continuity on an already fixed track."""

import numpy as np


def describe(probabilities):
    p = np.asarray(probabilities, dtype=float)
    assert p.ndim == 2 and len(p) >= 2 and p.shape[1] >= 1
    assert np.isfinite(p).all() and np.min(p) >= 0
    mass = p.sum(axis=1)
    assert np.max(mass) <= 1 + 1e-10
    clutter = np.maximum(0, 1 - mass)
    states = np.argmax(np.column_stack([clutter, p]), axis=1)
    both_signal = (states[:-1] > 0) & (states[1:] > 0)
    switches = (states[:-1] != states[1:]) & both_signal
    weighted_same = np.sum(p[:-1] * p[1:])
    weighted_pairs = np.sum(mass[:-1] * mass[1:])
    total_mass = float(mass.sum())
    return dict(
        windows=len(p),
        signal_mass=total_mass,
        map_changes=int(np.sum(states[:-1] != states[1:])),
        map_signal_pairs=int(both_signal.sum()),
        map_satellite_switches=int(switches.sum()),
        soft_same_numerator=float(weighted_same),
        soft_signal_pair_mass=float(weighted_pairs),
        soft_same_given_signal=float(weighted_same / weighted_pairs)
        if weighted_pairs > 0
        else None,
        dominant_satellite_share=float(p.sum(axis=0).max() / total_mass)
        if total_mass > 0
        else None,
    )
