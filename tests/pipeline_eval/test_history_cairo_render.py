from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import exact_named_raw
from reports.ALGO08.v3.history_cairo_render import binding
from reports.ALGO08.v3.history_risk_cairo_physical import clean, compare_artists


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


def test_shared_axis_witness_keeps_only_drawn_labels():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from reports.ALGO08.v3.history_cairo_artists import visible_ticks

    figure = Figure()
    first, last = figure.subplots(2, sharex=True)
    last.set_xticks([0., 0.5, 1.])
    FigureCanvasAgg(figure).draw()
    assert visible_ticks(first)[0] == []
    assert visible_ticks(last)[0] == [(0., "0.0"), (0.5, "0.5"), (1., "1.0")]


def test_drawn_track_bar_witness_serializes_without_precision_loss():
    import json
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from reports.ALGO08.v3.history_cairo_artists import stock_special

    figure = Figure(figsize=(16, 6))
    axes = figure.subplots()
    axes.bar(np.arange(3), [10.25, 95.125, 3.625], bottom=np.int64(0))
    assert isinstance(axes.patches[0].get_y(), np.integer)
    FigureCanvasAgg(figure).draw()
    restored = json.loads(json.dumps(stock_special(figure), allow_nan=False))
    assert restored["axes"][0]["bars"][0] == [-0.4, 0., 0.8, 10.25]


def test_history_proof_preserves_masks_and_counts_when_filtering_clocks():
    proof = dict(cpu_ns=10, lean_attempts=[dict(fine_exact_cpu_s=.01, conditional_mask=[True, False],
                                                wall_ns=21, elapsed_probe_calls=3, exterior_checks=0)])
    assert clean(proof) == dict(lean_attempts=[dict(conditional_mask=[True, False], elapsed_probe_calls=3,
                                                  exterior_checks=0)])
