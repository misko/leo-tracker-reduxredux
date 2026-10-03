from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.analysis.starlink import CFO_ALIAS_SPACING_HZ
from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
from leo.contracts.states import StarlinkEdge
from leo.presentation import scanner_track_overlay as overlay
from tests.analysis.test_persistent_hop_trajectory import _candidate


@pytest.fixture
def tracks():
    rows = tuple(
        _candidate(
            lane=lane,
            point=i,
            normalized_rate_hz_per_s=-2000,
            normalized_intercept_hz=50000,
            alias_index=int(i > 15),
        )
        for lane in (0, 1)
        for i in range(31)
    )
    return reconstruct_persistent_hop_trajectories(rows), rows


def test_tuning_removal_and_alias_copies_share_the_pilot_coordinate():
    pilot = starlink_edge_rf_center_frequency_hz(2, StarlinkEdge.LOWER)
    for detuning in (-20000, 0, 30000):
        rf = pilot + detuning
        for lift in (-2, 0, 3):
            raw = 1234 - detuning + lift * CFO_ALIAS_SPACING_HZ
            assert overlay.pilot_residual(raw, 2, StarlinkEdge.LOWER, rf) == pytest.approx(1234)


def test_alias_boundary_does_not_connect_opposite_edges():
    half = CFO_ALIAS_SPACING_HZ / 2
    segments = list(
        overlay.alias_segments(np.arange(4), np.array([half - 2, half - 1, -half, -half + 1]))
    )
    assert [list(t) for t, _ in segments] == [[0, 1], [2, 3]]


def test_overlay_uses_track_membership_and_correct_lane_coordinates(tracks, monkeypatch):
    trajectory, rows = tracks
    # An extra candidate near the curve is not a member and must not gain a ring.
    unassigned = replace(rows[0], candidate_id="sha256:" + "f" * 64, measured_cfo_hz=1234)
    figures = []
    monkeypatch.setattr(overlay, "_save", lambda fig: figures.append(fig) or b"png")
    origin = min(row.support_center_utc_ns for row in rows) - 5_000_000_000
    overlay.render_scanner_track_overlay_png(
        trajectory,
        (*rows, unassigned),
        capture_start_utc_ns=origin,
        capture_end_utc_ns=origin + 60_000_000_000,
    )
    fig = figures[0]
    assert len(fig.axes) == 4
    assert fig.axes[0].get_xlim() == (0, 60)
    assert len(fig.axes[1].collections) == 0  # CH2 must not inherit CH1/CH4 tracks.
    for axis, lane in ((fig.axes[0], 0), (fig.axes[3], 1)):
        rings = [c for c in axis.collections if c.get_zorder() == 5]
        assert len(rings) == 3
        assert all(len(c.get_offsets()) == 31 for c in rings)
        fitted = [line for line in axis.lines if line.get_zorder() == 4]
        assert fitted
        # Evaluate at the observation center, not at the earlier support boundary.
        row = rows[lane * 31]
        canonical = overlay.pilot_residual(
            row.measured_cfo_hz, row.channel, row.edge, row.actual_rf_hz
        )
        time = (row.support_center_utc_ns - origin) / 1e9
        assert np.interp(time, fitted[1].get_xdata(), fitted[1].get_ydata()) == pytest.approx(
            canonical, abs=1e-5
        )
    fig.clear()


def test_real_png_and_empty_track_overlay(tracks):
    trajectory, rows = tracks
    payload = overlay.render_scanner_track_overlay_png(replace(trajectory, tracklets=()), rows)
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
