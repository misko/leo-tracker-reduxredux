"""Match the original whitened joint sufficient statistics at numerical edges."""

import numpy as np
import pytest

from tools.pipeline_eval.qualification import cached_association as study
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.scoring import ARMS, ROLES
from tools.pipeline_eval.variants import cached_association as cache
from tools.pipeline_eval.variants import joint_orbits as joint
from tools.pipeline_eval.variants import robust_em as lean


def arc_and_state(cycles):
    rng = np.random.default_rng(116)
    n, count = 57, len(cycles)
    t = np.linspace(1, 55, n)
    whiten = np.eye(n) / 150 + np.tril(rng.normal(scale=1e-5, size=(n, n)), k=-1)
    track = lean.Track(t, np.zeros(n), 12.1e9, 2, True, (t - 27) / 100, whiten)
    xy = rng.normal(scale=55, size=(count, n, 2))
    phase = rng.normal(scale=120, size=(count, n))
    residual = np.array(cycles)[:, None] * lean.PERIOD + rng.normal(scale=112, size=(count, n))
    arc = lean.Arc(track, np.arange(count), residual, xy, phase, np.zeros(count), np.zeros(count))
    state = lean.State(
        np.array([2.7, -7.8]),
        np.array([0, 0, 350, 0]),
        np.array([0, 0, 45, 0]),
        np.linspace(-lean.PHASE_BOUND_S, lean.PHASE_BOUND_S, count),
        300.0,
    )
    return arc, state


@pytest.mark.parametrize("cycles", [[1, -2, 3, -4], [25_000, -20_000, 10_000, -40_000]])
def test_centered_form_preserves_aliases_and_bounded_profile(cycles):
    arc, state = arc_and_state(cycles)
    prepared = cache.prepare(arc)
    matches = cache.evaluate(arc, state, prepared)
    control = joint._matches(arc, state)
    assert matches is not None
    assert [(m.orbit, m.alias) for m in matches] == [(m.orbit, m.alias) for m in control]
    assert np.allclose([m.stats for m in matches], [m.stats for m in control], atol=1e-7, rtol=1e-8)
    assert np.allclose(
        [joint.phase_cost(m.stats) for m in matches],
        [joint.phase_cost(m.stats) for m in control],
        atol=1e-7,
        rtol=1e-8,
    )


@pytest.mark.parametrize("gap", [0.0, -1e-15, 1e-15, -1e-10, 1e-10])
def test_half_even_alias_uses_absolute_parity_and_stock_rounding(gap):
    n = 32
    t = np.arange(n, dtype=float)
    track = lean.Track(t, np.zeros(n), 11.5e9, 0, True, (t - 16) / 100, np.eye(n))
    slopes = np.broadcast_to(np.sin(t), (4, n)) * 300
    raw = (np.array([0.5, 1.5, -1.5, -2.5])[:, None] + gap) * lean.PERIOD + slopes
    arc = lean.Arc(
        track,
        np.arange(4),
        raw,
        np.zeros((4, n, 2)),
        np.broadcast_to(np.sin(t), (4, n)),
        np.zeros(4),
        np.zeros(4),
    )
    # The centered sinusoid supplies nonconstant residuals without moving the chosen half tie.
    arc.residual[:] -= slopes.mean(axis=1)[:, None]
    state = lean.State(np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(4), 0.0)
    matcher = cache.Matcher(joint._matches, cached=True)
    control = joint._matches(arc, state)
    actual = matcher(arc, state)
    assert [m.alias for m in actual] == [m.alias for m in control]
    if abs(gap) <= 1e-15:
        assert actual == control
        assert matcher.fallbacks == 1
    else:
        assert matcher.fallbacks == 0
        assert np.allclose([m.stats for m in actual], [m.stats for m in control], rtol=1e-10)


def test_cancelled_centered_energy_replays_directly():
    arc, state = arc_and_state([1, -2, 3, -4])
    track = arc.track
    radio = state.bias[track.lane] + track.drift * state.drift[track.lane]
    radio += (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    arc.residual[:] = np.arange(1, 5)[:, None] * lean.PERIOD + arc.xy @ state.xy + radio
    matcher = cache.Matcher(joint._matches, cached=True)
    assert matcher(arc, state) == joint._matches(arc, state)
    assert matcher.fallbacks == 1


def test_cache_is_prepared_once_for_repeated_states():
    arc, state = arc_and_state([1, -2, 3, -4])
    matcher = cache.Matcher(joint._matches, cached=True)
    for i in range(7):
        state.xy[0] += 0.01 * i
        assert [m.alias for m in matcher(arc, state)] == [
            m.alias for m in joint._matches(arc, state)
        ]
    report = matcher.receipt()
    assert report["calls"] == 7
    assert report["cached_tracks"] == 1
    assert 0 < report["gram_preparation_cpu_s"] < report["match_and_preparation_cpu_s"]


def test_sealed_charts_keep_matched_and_omitted_queries_separate():
    roof, omitted = screening_figures.charts([cache.METHOD], evidence=study.REPORT)
    assert roof.cases == study.MATCHED and roof.scope == "roof"
    assert omitted.cases == study.OMITTED and omitted.scope == "transfer"
    for arm in ARMS:
        roof_rows = roof.page(arm).rows
        assert set(ROLES) <= {row.series for row in roof_rows}
        assert sum(row.series == "one" and row.decision == "published" for row in roof_rows) == 5
        withheld = [row for row in omitted.page(arm).rows if row.series == "candidate"]
        assert len(withheld) == 2
        assert all(row.decision == "withheld" and row.error_km is None for row in withheld)
