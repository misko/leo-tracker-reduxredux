"""Full GLRT replays cover segment boundaries and preserve receiver inventories."""

from types import SimpleNamespace

import profile_algo07_full_glrt as full
import pytest


def test_spans_cover_each_native_window_once():
    source = {'segments': [{'windows': 129}, {'windows': 17}]}
    rows = list(full.spans(source))
    actual = [r['offset']+i for r in rows for i in range(r['start'], r['stop'])]
    assert actual == list(range(146))
    assert [(r['start'], r['stop']) for r in rows] == [(0, 64), (64, 128), (128, 129), (0, 17)]


def test_comparison_rejects_missing_receivers_and_changed_candidates(monkeypatch):
    monkeypatch.setattr(full.fixture, 'published_candidates', lambda r: r.candidates)
    a = SimpleNamespace(receiver_id=0, candidates=[{'fractional_margin': .04}])
    b = SimpleNamespace(receiver_id=1, candidates=[])
    expected = [dict(receiver_id=0, candidates=a.candidates), dict(receiver_id=1, candidates=[])]
    assert full.compare_receivers([a, b], expected)
    assert not full.compare_receivers([a], expected)
    a.candidates = [{'fractional_margin': .041}]
    assert not full.compare_receivers([a, b], expected)
    with pytest.raises(ValueError, match='duplicate'):
        full.compare_receivers([a, b], expected+expected)
