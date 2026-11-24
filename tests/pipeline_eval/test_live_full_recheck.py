"""The live callback and independently replayed frozen rule emit the same rows."""

from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from test_selective_full_recheck import row
import live_full_recheck as live
from selective_full_recheck import replace, shortlist
from tools.pipeline_eval.variants.carrier_continuation import Continuation


def factor(rank, epoch, *, status, offset, cfo, exact, control, margin):
    return dict(candidate_rank=rank, epoch=epoch, fractional_tracking_cfo_hz=cfo, fractional_margin=margin,
                passed_fractional_margin_gate=True)


def test_live_uses_same_window_and_second_native_contender(monkeypatch):
    measurements = [(0, 0, 32, 99_000.0, .6, .1), (1, 2, 21, -1000.0, .4, .1)]
    active = set()
    calls = []

    class Path:
        maximum = 2

        def __init__(self, library, asset, mode):
            active.add(mode)

        def run(self, samples, lane, center):
            assert active == {"full", "short_primary"}
            calls.append((samples, lane, center))
            return measurements, (7, 8)

    class Mixer:
        visits = Counter()

        @contextmanager
        def detector(self, *args, **kwargs):
            for mode in ("full", "short_primary"):
                live.mixed.NativePath(None, None, mode)

            def receive(window):
                self.visits[window.mode] += 1
                return window.rows

            yield receive
            active.clear()

    monkeypatch.setattr(live.mixed, "NativePath", Path)
    windows = []
    for i, cfo in enumerate((-1000., -1000., -1000., -1000., 80_000., None)):
        candidates = [] if cfo is None else [factor(0, 0, status="complete", offset=0, cfo=cfo,
                                                    exact=.4, control=.1, margin=.3)]
        windows.append(SimpleNamespace(rows=[row(i, 1+10_000_000*i, candidates)],
                                       mode="full" if i == 0 else "short_primary", samples=object(),
                                       target={"rf_center_hz": 24, "lnb_lo_hz": 10},
                                       acquisition={"actual_if_center_hz": 7}))
    base = [window.rows[0] for window in windows]
    entries = [(i, i, 0, None, "anchor" if i == 0 else "short", None) for i in range(len(windows))]
    expected, _ = shortlist(base, entries, Continuation())
    assert expected == {(4, 0)}
    replay, proof = replace(base, {(4, 0): live.full_candidates(measurements, factor)}, Continuation())
    adapter = live.LiveFullRecheck(Mixer(), Continuation, factor)
    with adapter.detector("cancellation", "lower") as receive:
        assert [item for window in windows for item in receive(window)] == replay
        assert live.mixed.NativePath is Path
    assert calls == [(windows[4].samples, 0, 7)]
    assert proof[0]["chosen"][0]["candidate_rank"] == 1
    assert adapter.receipt()["calls"][0]["replacement"] == proof[0]
    assert adapter.receipt()["native_cpu_ns"] == 7
    assert adapter.receipt()["extra_ci16_retained_bytes"] == 0
    assert not active


def test_compatible_scope_rejects_alternate_input_and_holds():
    values = dict(eight_ms_native_history=True, sparse8_primary=True, held_anchor_route=True)
    live.require_compatible(SimpleNamespace(**values))
    for option, value in (("held_anchor_route", False), ("sparse8_primary", False),
                          ("whole_stereo_blocks", True), ("full_anchor_primary_library", "library"),
                          ("packed_ci16_map", "map"), ("select_before_cfo", True)):
        with pytest.raises(ValueError, match="original signed sparse"):
            live.require_compatible(SimpleNamespace(**(values | {option: value})))
