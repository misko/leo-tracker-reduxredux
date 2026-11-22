from io import BytesIO

import matplotlib as mpl
import pytest
from PIL import Image

from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.contracts.fast_standard_analysis import ALGO08V2
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak
from tools.pipeline_eval.variants.experimental import raster_layout


def _packet():
    curves = tuple(OrbitCurve(str(1000 + index), (0., 105., 210., 300.),
                              (0., PERIOD * .45, -PERIOD * .4, float("nan")))
                   for index in range(9))
    peaks = (OrbitPeak("a", 105., PERIOD * .45, "1000"),
             OrbitPeak("b", 212., -PERIOD * .4))
    center = [-35.92369, 133.02345]
    residual = dict(norad=1000, component="track-µ1", receiver=1, channel=1,
                    time_s=105., residual_hz=-350.5)
    return dict(
        selected_model=ALGO08V2,
        observations=[dict(observation_id="a", receiver=1, channel=1),
                      dict(observation_id="b", receiver=1, channel=1)],
        rows=dict(fitted_c=[residual], c0=[dict(residual, residual_hz=-610.2)]),
        orbit_lanes=(OrbitLane("RX1", "CH1", peaks, curves),
                     OrbitLane("RX2", "CH3", (), ()),
                     OrbitLane("RX1", "CH8", (), curves[:1])),
        arms=dict(fitted_c=dict(endpoint_latlon=[-36.02, 133.37]),
                  c0=dict(endpoint_latlon=[-35.19, 133.4])),
        position_grid=dict(region_center=center, box_width_km=185., complete=False,
                           evaluated_points=2, planned_points=4,
                           points=[dict(east_km=1., north_km=-92.5, scores=dict(fitted_c=26.2)),
                                   dict(east_km=9., north_km=13., scores=dict(fitted_c=None))]),
    )


@pytest.mark.skipif(mpl.__version__ != raster_layout._QUALIFIED_MATPLOTLIB,
                    reason="Direct layout is qualified on the release's Matplotlib")
def test_complete_render_keeps_unequal_group_sizes_and_a_moved_regional_map():
    packet = _packet()
    options = dict(title="Unequal receiver lanes · Ω",
                   evaluation_reference=dict(latitude_deg=-36.1, longitude_deg=132.9))
    with mpl.rc_context(mpl.rcParamsDefault):
        control = raster_layout.render_shared_pixels(packet, **options)
        candidate = raster_layout.render_layout(packet, require_trial=True, **options)
    assert candidate == control
    assert len(candidate) == 8
    with (Image.open(BytesIO(candidate["ch1-4-all"])) as left,
          Image.open(BytesIO(candidate["ch5-8-all"])) as right):
        assert left.width == right.width
        assert left.height > right.height


def test_changed_style_uses_shared_pixel_fallback():
    packet = _packet()
    with mpl.rc_context({"axes.titley": .93, "figure.dpi": 112}):
        control = raster_layout.render_shared_pixels(packet, title="Changed style")
        assert raster_layout.render_layout(packet, title="Changed style") == control
        with pytest.raises(raster_layout.UnsupportedLayout, match="style"):
            raster_layout.render_layout(packet, title="Changed style", require_trial=True)


@pytest.mark.skipif(mpl.__version__ != raster_layout._QUALIFIED_MATPLOTLIB,
                    reason="Direct layout is qualified on the release's Matplotlib")
def test_geometry_guard_falls_back_if_other_column_changes_spacing(monkeypatch):
    packet = _packet()
    stock_title = raster_layout._DiscardedColumn.set_title

    def taller_title(self, text, *, fontsize):
        stock_title(self, f"{text}\nRaised\nTitle", fontsize=fontsize)

    monkeypatch.setattr(raster_layout._DiscardedColumn, "set_title", taller_title)
    with mpl.rc_context(mpl.rcParamsDefault):
        control = raster_layout.render_shared_pixels(packet, title="Changed geometry")
        assert raster_layout.render_layout(packet, title="Changed geometry") == control
        with pytest.raises(raster_layout.UnsupportedLayout, match="row spacing"):
            raster_layout.render_layout(packet, title="Changed geometry", require_trial=True)
