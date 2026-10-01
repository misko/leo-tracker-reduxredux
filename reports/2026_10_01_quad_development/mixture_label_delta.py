"""Exact fixed-state residual-group correction for one assignment change."""
from scale_mixture import mixture, components


def correction(rows):
    if len(rows) <= 1: return 0.
    return mixture(rows)-components(rows)[0]


def move_gain(groups, old_key, new_key, track_index, new_stat, physical_change):
    if old_key == new_key: return float(physical_change)
    gain = float(physical_change)
    for key in {old_key, new_key}-{None}:
        original = groups.get(key, {})
        modified = dict(original)
        if key == old_key: del modified[track_index]
        if key == new_key: modified[track_index] = new_stat
        gain += correction(list(modified.values()))-correction(list(original.values()))
    return gain
