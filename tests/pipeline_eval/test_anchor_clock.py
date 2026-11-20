"""Verify the anchor-held evidence never changes when the final clock is added."""

from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import anchor_clock as model
from tools.pipeline_eval.variants import robust_em as lean


def _profile(orbit, suffix_hz=0):
    t = np.arange(12.0) * 3
    hz = np.r_[np.zeros(8), np.full(4, suffix_hz)]
    track = lean.Track(t, hz, 11.5e9, 0, True, t / 100, np.eye(12))
    arc = lean.Arc(
        track, np.array([orbit]), hz[None], np.zeros((1, 12, 2)),
        np.ones((1, 12)), np.zeros(1), np.zeros(1),
    )
    return model.anchor.prefix(arc)


def _state(clock=False):
    return model.smooth.ClockState(
        np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(4), 0.0,
        np.zeros((2, len(model.smooth.CENTER_S))) if clock else None,
    )


def test_suffix_perturbation_cannot_change_its_prefix_phase_or_alias():
    before, after = _profile(0), _profile(0, suffix_hz=600)
    locked = lean.Assignment(before.train, 0, 0, 0.0, 0.8)
    base = model._suffix(before, locked, _state(clock=True))
    shifted = model._suffix(after, locked, _state(clock=True))
    np.testing.assert_allclose(shifted - base, 600)
    assert before.train.track.hz.tolist() == after.train.track.hz.tolist()


def test_diagnostic_uses_only_other_prefixes_and_same_support_for_both_models(monkeypatch):
    profiles = [_profile(j, suffix_hz=100 + j) for j in range(4)]
    nominated = [(p, lean.Assignment(p.train, 0, 0, 0.0, 0.8)) for p in profiles]
    calls = []

    def fit(rows, count, half, arm, *, clock):
        assert len(rows) == 3
        assert all(len(r.arc.track.t) == 8 and not np.any(r.arc.track.hz) for r in rows)
        calls.append((tuple(r.orbit for r in rows), arm, clock))
        return SimpleNamespace(state=_state(clock))

    monkeypatch.setattr(model.smooth, "fit", fit)
    result = model._held(nominated, 4, 12.5)
    assert len(calls) == 16
    for a, b in zip(calls[::2], calls[1::2], strict=True):
        assert a[:2] == b[:2]
        assert a[2] is False and b[2] is True
    for record in result.values():
        assert record["held_points"] == 16
        assert record["held_tracks"] == 4
        assert record["linear_rms_hz"] == record["clock_rms_hz"]


def test_paired_variant_passes_the_identical_final_owner_list_and_initial_fit(monkeypatch):
    selected = [lean.Assignment(_profile(0).arc, 0, 3, 0.1, 1.0)]
    start = lean.Fit(_state(), 10.0, 1.0, 1.0)
    region = SimpleNamespace(site=lambda xy: (None, [float(xy[0]), float(xy[1])]))
    seen = []

    def original(rows, initial, tile, region, half, arm):
        seen.append(("linear", rows, initial, arm))
        return start, {}

    def clock(rows, initial, tile, region, half, arm, *, clock):
        assert clock
        seen.append(("clock", rows, initial, arm))
        return start, {"accepted": True}

    def anchor_infer(document, offer, catalogue):
        owners = model.anchor.validated([], 1, 12.5)
        for arm in lean.ARMS:
            model.exact.refine(owners, start, None, region, 12.5, arm)
        return dict(status="ok", reason=None, metrics={"anchor_tracks": 1},
                    arms={a: {"latlon": [0.0, 0.0]} for a in lean.ARMS})

    monkeypatch.setattr(model.anchor, "validated", lambda *_: selected)
    monkeypatch.setattr(model.anchor, "infer", anchor_infer)
    monkeypatch.setattr(model.smooth, "refine", clock)
    monkeypatch.setattr(model.exact, "refine", original)
    result = model.paired({}, {}, "", diagnose=False)
    for arm, a, b in zip(lean.ARMS, seen[::2], seen[1::2], strict=True):
        assert a[0] == "clock" and b[0] == "linear"
        assert a[1] is b[1] is selected
        assert a[2] is b[2] is start
        assert a[3] == b[3] == arm
    candidate, measured = result["result"], result["linear_result"]
    assert candidate["metrics"]["anchor_ownership"] == measured["metrics"]["anchor_ownership"]
    assert candidate["metrics"]["anchor_held_model"] == measured["metrics"]["anchor_held_model"]
    assert result["held_diagnostic"] == {}
