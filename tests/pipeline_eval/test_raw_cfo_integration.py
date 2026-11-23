"""Verify that the raw refinement keeps the original receiver evidence contract."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import mixed_aperture_receiver as mixed
import short_cfo_raw as refined
from raw_cfo_0016_score import compare_factors, matched_rms


def probe(lane):
    candidate = dict(zip(refined.FIELDS, (0, 19, -0.25, -321.0, 0.8, 0.2), strict=True))
    return dict(receiver_id=lane, visit_index=7, candidates=[candidate | {
        "fractional_margin": 0.6, "passed_fractional_margin_gate": True,
    }])


def policy_for(calls):
    def diagnostics(full, waveform, lane, rows):
        calls.append((lane, full, waveform, rows))
        return (0,)

    def amend(rows, diagnostic, step, center):
        assert diagnostic == (0,) and step == 1.0 and center == 100
        (row,) = rows
        return ((row[:3] + (row[3] + 12.0,) + row[4:]),), "updated"

    return SimpleNamespace(refiner=SimpleNamespace(diagnostics=diagnostics), amend=amend)


def test_same_selected_factor_except_signed_frequency():
    original = probe(1)
    calls = []
    updated, reason, changed = refined.refined_probe(original, "waveform", "verifier", policy_for(calls), 100)
    assert changed and reason == "updated"
    assert calls[0][:3] == (1, "verifier", "waveform")
    assert updated["candidates"][0] == original["candidates"][0] | {refined.CFO: -309.0}
    assert original["candidates"][0][refined.CFO] == -321.0


def test_receiver_wraps_positive_short_lanes_only_and_releases_its_context(monkeypatch):
    from contextlib import contextmanager

    calls, closed = [], []

    @contextmanager
    def original(self, *_, **__):
        def receive(window):
            self.visits[window.mode] += 1
            return [probe(0), dict(probe(1), candidates=[]) if window.empty else probe(1)]
        yield receive

    monkeypatch.setattr(mixed.MixedApertureDetector, "detector", original)
    monkeypatch.setattr(mixed, "verified", lambda *_: np.zeros(2, dtype="<f4").tobytes())
    monkeypatch.setattr(mixed, "NativePath", lambda *_: SimpleNamespace(close=lambda: closed.append(True)))
    runner = refined.RefinedShortDetector(Path("short.so"), "pin", full_coverage=True, policy=policy_for(calls))
    window = SimpleNamespace(mode="full", empty=False, samples=object(),
                             target=dict(rf_center_hz=100, lnb_lo_hz=0), acquisition=dict(actual_if_center_hz=0))
    with runner.detector("cancellation", "lower") as receiver:
        assert receiver(window) == [probe(0), probe(1)]
        window.mode, window.empty = "short_primary", True
        assert receiver(window)[1]["candidates"] == []
        window.empty = False
        receiver(window)
    assert [row[0] for row in calls] == [0, 0, 1]
    assert all(row[2] is window.samples for row in calls)
    assert closed == [True]


def test_unfrozen_lane_selection_cannot_enter_refined_cli():
    with pytest.raises(ValueError, match="original unfiltered short-primary"):
        refined.run_cli(Path("missing"), ["--short-lane-mask=target"])


def test_factor_audit_uses_the_original_anchor_and_primary_on_both_radios():
    rows = [dict(probe(lane), edge="lower", channel=3, actual_rf_hz=11209687500.0, visit_index=visit,
                 valid_start_counter=visit*200000) for visit in (1, 2) for lane in (0, 1)]
    baseline = dict(source=dict(session_id="fast-fixture", probes=rows))
    updated = deepcopy(baseline)
    updated["source"]["probes"][3]["candidates"][0][refined.CFO] += 15
    result, labels = compare_factors(baseline, baseline, updated)
    assert len(labels) == 4
    assert [(row["radio"], row["visit"], row["change_hz"]) for row in result["changes"]] == [(1, 2, 15)]
    assert matched_rms(result["reference"])["worsened"] == 1
    updated["source"]["probes"][3]["candidates"][0]["fractional_margin"] += 0.01
    with pytest.raises(ValueError, match="non-CFO factor"):
        compare_factors(baseline, baseline, updated)
