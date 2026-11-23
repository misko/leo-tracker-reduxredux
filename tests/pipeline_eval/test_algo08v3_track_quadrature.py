from importlib import import_module
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def quad(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("track_quadrature")


def track(key, n, rx=1):
    times = np.arange(n, dtype=float) ** 2
    return dict(key=key, times=times, values=times + 12, observation_ids=[f"{key}-{i}" for i in range(n)],
                receiver=rx, channel=1, rf_hz=10.9e9)


def test_spread_keeps_every_track_endpoints_measurements_and_short_tracks(quad):
    spread = run_path(str(quad.SAMPLER))["spread"]
    original = [track("curved", 50), track("predictive", 8, rx=2)]
    expanded, short = quad.sample_tracks(original, spread)
    assert expanded["key"] == original[0]["key"] and short["key"] == original[1]["key"]
    assert len(expanded["times"]) == 16 and all(np.diff(expanded["times"]) > 0)
    ids = [original[0]["observation_ids"].index(value) for value in expanded["observation_ids"]]
    assert ids[0] == 0 and ids[-1] == 49
    np.testing.assert_array_equal(expanded["times"], original[0]["times"][ids])
    np.testing.assert_array_equal(expanded["values"], original[0]["values"][ids])
    assert short["observation_ids"] == original[1]["observation_ids"]
    np.testing.assert_array_equal(short["times"], original[1]["times"])


def test_reexpanded_trim_uses_original_span_without_extrapolation(quad):
    full = track("curve", 10)
    sample = quad.sample_tracks([full], lambda _: np.array([0, 2, 7, 9]))[0]
    restored = quad.expand_track(full, sample, [False, True, True, False])
    assert np.flatnonzero(restored).tolist() == [2, 3, 4, 5, 6, 7]
    assert quad.expand_track(full, sample, [True] * 4).all()
    assert not quad.expand_track(full, sample, [False] * 4).any()
    with pytest.raises(ValueError, match="contiguous interval"):
        quad.expand_track(full, sample, [True, False, True, False])
    sample["values"][0] = -1
    with pytest.raises(ValueError, match="original measured track"):
        quad.expand_track(full, sample, [True] * 4)


def test_expansion_restores_predictive_ids_with_unchanged_aliases_and_real_receiver_support(quad):
    originals = [track("x", 9), track("y", 10, 2), track("linear", 12)]
    sample = quad.sample_tracks(originals, lambda times: np.array([0, 2, len(times) - 1]))
    full = SimpleNamespace(norads=np.array([42]), tracks=originals, curved=[0, 1])
    short = SimpleNamespace(norads=full.norads, tracks=sample, curved=full.curved)
    rows = [dict(component="x", candidate_index=0), dict(component="y", candidate_index=0)]
    node = dict(seed=dict(rows=rows), aliases=[-1, 0])
    basis = SimpleNamespace(rows=rows, members=[0, 1], slices=[slice(0, 3), slice(3, 6)])
    entries = [dict(track_index=2, component="linear", candidate_index=0, norad=42, alias=1,
                    points=3, observation_ids=sample[2]["observation_ids"], cross_receiver_curved_support=False)]
    keep, actual = quad.expand_support(full, short, node, np.ones(6, bool), basis, entries)
    assert keep.tolist() == [True] * 19
    assert node["aliases"] == [-1, 0]
    assert actual[0] == dict(entries[0], points=12, observation_ids=originals[2]["observation_ids"],
                            cross_receiver_curved_support=True)
    short.norads = np.array([99])
    with pytest.raises(ValueError, match="different orbit labels"):
        quad.expand_support(full, short, node, np.ones(6, bool), basis, entries)


def test_failed_quadrature_runs_installed_fallback_on_original_input(quad):
    module = import_module("blind_joint_route")
    attempts = []
    original = object()
    called = []

    def installed(prepared, region, bound, stages, *, selected_evidence):
        called.append(prepared)
        return {"status": "withheld"}

    def rejected(prepared, region, bound, observed, **kwargs):
        assert prepared is original
        return None, "full_geometry"

    route = module.make_route(installed, None, attempts, repair=True, signed_finish=True, joint_proposal=rejected)
    assert route(original, None, None, {}) == {"status": "withheld"}
    assert called == [original]
    assert attempts[0]["decision"] == "fallback"
    assert attempts[0]["reason"] == "full_geometry"
    assert attempts[0]["fallback_clocks"]["cpu_s"] >= 0
