from importlib import import_module
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def direct(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("one_pass_web_png")


@pytest.mark.parametrize(
    ("size", "rows", "columns", "field", "dpi"),
    [
        ((15, 11), 4, 2, "residual_figures", 125),
        ((16, 6), 1, 1, "track_figures", 125),
        ((14, 8), 1, 2, "position_figures", 120),
    ],
)
def test_explicit_layout_draws_original_data_and_pixel_dimensions(
    direct, size, rows, columns, field, dpi,
):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from tools.pipeline_eval.variants.experimental import raster_layout

    with direct.one_pass_layout(enabled=True) as work:
        figure = raster_layout._LayoutFigure(figsize=size, layout="constrained")
        canvas = FigureCanvasAgg(figure)
        axes = figure.subplots(rows, columns, squeeze=False)
        for axis in axes.flat:
            axis.plot([-1., 4., 8.], [3., 20., -1.], label="Original curve")
            axis.set(xlabel="Time (s)", ylabel="CFO residual (Hz)", title="Receiver · CH1")
        axis = axes.flat[0]
        if field == "track_figures":
            label = "my-long-session-with-ascii-and-µ-RX1-CH2-T032-RF11.456034"
            axis.set_xticks([4.], [label + "\n1000 · 23 pts"], rotation=90, fontsize=5)
        if field == "position_figures":
            colored = axis.scatter([1., 2.], [-1., 0.], c=[0., 3.])
            figure.colorbar(colored, ax=axis, label="Conditional fitted-c objective")
            figure.supxlabel("Search centre (−35.92369°, 133.02345°)")
        figure.suptitle("Study recording · 185 km search")
        stream = BytesIO()
        figure.savefig(stream, dpi=dpi, format="png")
        assert axis.lines[0].get_xdata().tolist() == [-1., 4., 8.]
        assert axis.lines[0].get_ydata().tolist() == [3., 20., -1.]
        assert axis.get_ylabel() == "CFO residual (Hz)"
        assert dict(work) == {field: 1}
        assert canvas.figure is figure
        if field == "track_figures":
            bbox = axis.get_xticklabels()[0].get_window_extent(canvas.get_renderer())
            assert bbox.y0 > 0
            assert axis.get_xticklabels()[0].get_text().splitlines()[0] == label
    with Image.open(stream) as image:
        assert image.size == tuple(side * dpi for side in size)


def test_unknown_figure_reuses_stock_without_hiding_plot_error(direct):
    from tools.pipeline_eval.variants.experimental import raster_layout

    calls = []
    original = raster_layout._LayoutFigure

    def renderer(packet, **options):
        calls.append((packet, options))
        raster_layout._LayoutFigure(figsize=(12, 5), layout="tight")
        assert raster_layout._LayoutFigure is original
        return "stock"

    actual, counts = direct.render(renderer, "evidence", enabled=True, title="Plot")
    assert actual == "stock"
    assert "layout_fallback" in counts
    assert calls == [("evidence", {"title": "Plot"})] * 2

    def broken(*args, **options):
        raise ValueError("original plot rejected malformed data")

    with pytest.raises(ValueError, match="rejected malformed"):
        direct.render(broken, None, enabled=True)


def test_orbit_template_preserves_lane_order_curve_and_selection(direct, monkeypatch):
    from leo.presentation import orbit_plot
    from tools.pipeline_eval.variants.experimental import raster_layout

    first = orbit_plot.OrbitLane(
        "RX1", "CH1", (orbit_plot.OrbitPeak("a", 105., 4500., "27"),),
        (orbit_plot.OrbitCurve("27", (0., 105., 210., 300.), (0., 4500., -4000., 500.)),),
    )
    second = orbit_plot.OrbitLane("RX2", "CH2", (orbit_plot.OrbitPeak("b", 200., 0.),))
    with direct.one_pass_layout(enabled=True) as counts:
        monkeypatch.setattr(orbit_plot, "Figure", raster_layout._OrbitFigure)
        figure = orbit_plot.make_orbit_plot(
            (first, second), panel="all", title="Offered region", alias_period_hz=10000.,
            time_limits_s=(0, 300),
        )
        figure.canvas.draw()
        assert [axis.get_title().split(" · ")[:2] for axis in figure.axes] == [
            ["RX1", "CH1"], ["RX2", "CH2"],
        ]
        assert len(figure.axes[0].lines[0].get_xdata()) > 4
        assert len(figure.axes[0].collections) == 2
        assert len(figure.axes[1].collections) == 1
        assert dict(counts) == {"orbit_figures": 1}
