from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import exact_named_raw
from reports.ALGO08.v3.history_cairo_render import binding
from reports.ALGO08.v3.history_risk_cairo_physical import compare_artists


def test_renderer_option_only_substitutes_the_ordinary_render_call():
    def original(packet, **options):
        return packet, options

    @contextmanager
    def orbit(installed, audit):
        assert installed is original
        audit["native_orbit_figures"] = 4
        yield

    def residual(installed, packet, *, explicit_layout, **options):
        assert installed is original and explicit_layout
        return installed(packet, **options), dict(native_residual_figures=2, position_figures=1, track_figures=1)

    scan, audit = SimpleNamespace(render=original), {}
    with (patch("direct_orbit_entry.native_orbits", orbit), patch("direct_residual_entry.render", residual),
          binding(scan, audit)):
        assert scan.render("packet", title="chart") == ("packet", {"title": "chart"})
        with pytest.raises(ValueError, match="one complete"):
            scan.render("packet")
    assert scan.render is original and audit["native_orbit_figures"] == 4 and audit["native_residual_figures"] == 2


def test_cairo_is_an_independent_prior_opt_in():
    common = [item for name in ("recording", "archive", "region", "output", "short-binary", "geographic-library",
                               "regional-track-library", "frontier-block-library", "archive-sha256")
              for item in ("--"+name, "test")]
    assert not exact_named_raw.parser().parse_args(common).cairo_six_sheets
    parsed = exact_named_raw.parser().parse_args([*common, "--cairo-six-sheets", "--history-risk-route"])
    assert parsed.cairo_six_sheets and parsed.history_risk_route and parsed.prove_no_active_curvature


def test_artist_limits_are_sealed_but_residual_ticks_may_change():
    from copy import deepcopy

    axis = {"xlim": [0, 300], "offsets": []}
    sheet = {"heading": "physical", "axes": [axis], "ticks": [[[], []]]}
    stock = dict(orbit=[sheet, sheet], residual=[sheet, sheet], standard={"track-rms": sheet, "position": sheet})
    plotted = deepcopy(stock)
    plotted["residual"][0] = dict(sheet, ticks=[[[[0, "0"]], []]])
    assert compare_artists(stock, plotted)["ch1-4-residuals"]["changed_tick_sets"] == 1
    plotted["residual"][0] = dict(sheet, axes=[dict(axis, xlim=[0, 250])])
    with pytest.raises(ValueError, match="xlim"):
        compare_artists(stock, plotted)
