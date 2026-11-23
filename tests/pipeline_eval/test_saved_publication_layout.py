from importlib import import_module
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture
def prepass(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("saved_publication_layout").layout_only_prepass


def draw(prepass, enabled, *, crop=None, callbacks=False):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(5, 3), layout="constrained")
    canvas = FigureCanvasAgg(figure)
    left, right = figure.subplots(1, 2)
    left.scatter([-5., -4., 0.], [-130., 0., 35.], c=[1., 2., 3.])
    left.set(ylabel="wrapped Hz", title="Short aperture", xlabel="Offset")
    right.plot([0., 3., 10.], [0., 1., -1.], label="Residuals")
    right.legend()
    right.set_aspect("equal")
    right.annotate("cold-start history", (3., 1.), xytext=(0, 7), textcoords="offset points")
    figure.suptitle("Both antennas")
    events = []
    if callbacks:
        canvas.mpl_connect("draw_event", lambda event: events.append(event.renderer.width))
    stream = BytesIO()
    with prepass(enabled=enabled) as stats:
        figure.savefig(stream, format="png", dpi=125, bbox_inches=crop)
    return stream.getvalue(), stats, events


def test_ordinary_layout_omits_prepass_artists_and_keeps_png_bytes(prepass):
    import matplotlib as mpl

    stock, old, _ = draw(prepass, False)
    candidate, new, _ = draw(prepass, True)
    assert stock == candidate
    if mpl.__version__ == "3.11.1":
        assert old["prepasses"] == new["prepasses"] == new["layout_only"] == 1
        assert old["layout_only"] == 0
    else:
        assert not old and not new


@pytest.mark.parametrize("crop,callbacks", [("tight", False), (None, True)])
def test_nonordinary_save_uses_original_agg_draw(prepass, crop, callbacks):
    stock, _, expected_events = draw(prepass, False, crop=crop, callbacks=callbacks)
    candidate, stats, events = draw(prepass, True, crop=crop, callbacks=callbacks)
    assert stock == candidate
    assert events == expected_events
    assert stats["layout_only"] == 0


def test_reverse_switches_the_first_and_last_arms(prepass):
    trial = import_module("saved_publication_trial")
    assert trial.ORDER == ("installed", "layout", "layout", "installed")
    assert trial.REVERSED_ORDER == ("layout", "installed", "installed", "layout")
