"""Bounded native-window selection preserves paired receiver evidence."""

import pytest
from profile_algo07_glrt import locate, select_visits


def test_seeded_channel_stratification_uses_whole_unique_windows():
    probes = [dict(visit_index=8*k+ch-1, channel=ch, receiver_id=rx)
              for k in range(10) for ch in range(1, 9) for rx in (0, 1)]
    selected = select_visits(probes)
    assert selected == select_visits(list(reversed(probes)))
    assert len(selected) == len(set(selected)) == 16
    assert all(sum(v % 8 == ch for v in selected) == 2 for ch in range(8))
    assert selected != select_visits(probes, seed=0)
    with pytest.raises(ValueError, match='eight'):
        select_visits([p for p in probes if p['channel'] != 8])
    with pytest.raises(ValueError, match='conflicting'):
        select_visits(probes+[dict(visit_index=0, channel=8)])


def test_segment_selection_respects_published_inventory_bounds():
    rows = [dict(windows=10), dict(windows=4)]
    inventory = dict(segments=rows)
    assert locate(inventory, 9) == (rows[0], 9)
    assert locate(inventory, 10) == (rows[1], 0)
    assert locate(inventory, 13) == (rows[1], 3)
    for invalid in (-1, 14):
        with pytest.raises(ValueError, match='outside'):
            locate(inventory, invalid)
