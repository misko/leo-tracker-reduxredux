from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.qualification import train_update_results as results
from tools.pipeline_eval.variants import train_update as candidate


def test_held_clock_and_phase_predictions_preserve_a_single_alias_and_equal_arm_owners(monkeypatch):
    t = np.array([0.0, 0.1, 0.3, 1.0])
    pattern = 100 * t**2
    track = SimpleNamespace(
        rf=12e9,
        lane=1,
        t=t,
        drift=t / 100,
        whiten=np.eye(4),
        hz=pattern + candidate.lean.PERIOD + 6.0,
    )
    arc = SimpleNamespace(track=track, orbit=np.array([0, 1]))
    state = candidate.lean.State(np.zeros(2), np.array([0, 6.0]), np.zeros(2), np.zeros(2))

    def project(tile, orbit, times, site, phase, rf):
        return (pattern if orbit == 1 else -pattern), None, None

    monkeypatch.setattr(candidate.exact, "project", project)
    free = candidate.held_row(arc, None, np.zeros(3), state)
    assert (free.winner, free.alias, free.loss) == (1, 1, 0)
    assert free.margin > 0.25
    state.c_hz_per_ghz = 2 * candidate.lean.PERIOD
    locked = candidate.held_row(arc, None, np.zeros(3), state, free)
    assert (locked.winner, locked.alias) == (free.winner, free.alias)
    assert np.isclose(locked.loss, candidate.lean.PERIOD**2)
    assert candidate.held_metrics([free])["held_orbits"] == 1
    assert candidate.held_metrics([locked])["held_orbits"] == 0


def test_no_publication_when_fixed_owner_geometry_or_geographic_evidence_is_weak():
    metrics = dict(
        orbit_count=4,
        curved_fit_tracks=4,
        distinct_radio_lanes=2,
        separated_orbits=3,
        held_orbits=2,
        held_score=0.28,
        pooled_shift_km=4,
    )
    fit = SimpleNamespace(radius_km=6.0, state=SimpleNamespace(xy=np.array([0.0, 0.0])))
    fits = {arm: fit for arm in candidate.lean.ARMS}
    assert candidate.decision(metrics, fits, 12.5) is None
    assert (
        candidate.decision(metrics | {"pooled_shift_km": 4.01}, fits, 12.5)
        == "weak_position_geometry"
    )
    assert (
        candidate.decision(metrics | {"held_score": 0.27}, fits, 12.5) == "weak_held_track_support"
    )
    fit.state.xy[1] = 11.75
    assert candidate.decision(metrics, fits, 12.5) == "position_at_tile_boundary"
    assert candidate.solve([], None, None, 12.5) == ({}, {}, "insufficient_track_blocks")


def test_control_must_have_same_native_input_and_anonymous_tracks_even_when_withheld():
    row = dict(
        id="case",
        cohort="roof",
        tile={"center": [1, 2]},
        recording="A",
        result=dict(status="ok"),
        input_sha256="request",
        native_sha256="native",
        catalog_sha256="causal",
        observation_sha256="arcs",
    )
    control = row | {"result": dict(status="withheld")}
    results.matched(row, control)
    for key in ("native_sha256", "catalog_sha256", "input_sha256", "observation_sha256"):
        with pytest.raises(ValueError):
            results.matched(row, control | {key: "different"})


def test_fixed_owner_roof_and_omitted_charts_keep_all_queried_recordings_in_both_arms():
    charts = screening_figures.charts(evidence=results.trial.REPORT)
    roof = next(c for c in charts if c.scope == "roof")
    omitted = next(c for c in charts if c.scope == "transfer")
    for arm in results.ARMS:
        marks = roof.page(arm).rows
        for dataset, count in (("DS26", 127), ("DS29", 8)):
            for key in (*results.ROLES, "one", "stock"):
                selected = [m for m in marks if m.dataset == dataset and m.series == key]
                assert len({m.recording for m in selected}) == len(selected) == count
        candidate_rows = [m for m in marks if m.series == "one"]
        assert sum(m.decision == "published" for m in candidate_rows) == 133
        assert all((m.error_km is not None) == (m.decision == "published") for m in candidate_rows)
        alternate = [m for m in omitted.page(arm).rows if m.series == "candidate"]
        assert len(alternate) == 9 and all(m.decision == "withheld" for m in alternate)
