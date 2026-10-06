from io import BytesIO

import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

from leo.contracts.regional_position_products import RegionalPositionDocumentV1
from leo.presentation.regional_position import regional_position_figure, render_regional_position
from tests.contracts.test_regional_position_products import document


@pytest.mark.parametrize("method", ["T1AT", "V16"])
def test_insufficient_support_still_has_a_real_labeled_png(method):
    doc = document()
    figure = regional_position_figure(doc, method)
    axis = figure.axes[0]
    assert "unavailable (no-windows)" in axis.get_title()
    assert axis.get_xlim() == (-250, 250)
    assert axis.get_ylim() == (-250, 250)
    assert axis.get_aspect() == 1
    assert [line.get_label() for line in axis.lines] == ["Reference (evaluation only)"]
    image = Image.open(BytesIO(render_regional_position(doc, method)))
    assert image.format == "PNG"
    assert image.size == (1080, 960)


def test_maps_distinguish_rf_arms_reference_and_likelihood_units():
    payload = document().model_dump(mode="json")
    payload["windows"] = 50
    selected = dict(
        latitude_deg=38,
        longitude_deg=-122,
        east_km=-70,
        north_km=-80,
        objective=120,
        calibration_penalty=2,
        selection_score=122,
        posterior_rms_hz=100,
        signal_windows=40,
        stationarity=0.0001,
        converged=True,
        boundary=False,
        coefficient_hz_per_ghz=0,
        horizontal_error_m=5700,
        satellites=[1, 2],
        associated_windows=40,
        source_basin="basin-0",
        stop_reason="stationary",
    )
    method = payload["methods"][0]
    method["state"] = "diagnostic"
    method["points"] = [dict(east_km=0, north_km=0, spacing_km=100, objective=150, converged=True)]
    for arm in method["arms"]:
        arm.update(selected=dict(selected), completed_starts=2, reasons=[])
    method["arms"][0]["selected"]["coefficient_hz_per_ghz"] = 20
    method["arms"][1]["selected"].update(east_km=-60, horizontal_error_m=10000)
    doc = RegionalPositionDocumentV1.model_validate(payload)
    figure = regional_position_figure(doc, "T1AT")
    axis = figure.axes[0]
    assert [line.get_label() for line in axis.lines] == [
        "fitted-c selected estimate",
        "zero-c selected estimate",
        "Reference (evaluation only)",
    ]
    assert "5.70 km" in axis.get_title() and "10.00 km" in axis.get_title()
    assert "negative log likelihood" in figure.axes[1].get_ylabel()
    assert "in-sample" in figure._supxlabel.get_text()
    bad = doc.model_dump(mode="json")
    bad["methods"][0]["arms"][1]["selected"]["coefficient_hz_per_ghz"] = 20
    with pytest.raises(ValueError, match="zero-c"):
        RegionalPositionDocumentV1.model_validate(bad)


def test_long_partial_band_reason_fits_inside_png_canvas():
    payload = document().model_dump(mode="json")
    for method in payload["methods"]:
        for arm in method["arms"]:
            arm["reasons"] = [
                "partial-band filtered-pilot evidence is candidate-only "
                "and not qualified for positioning"
            ]
    figure = regional_position_figure(RegionalPositionDocumentV1.model_validate(payload), "T1AT")
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    bounds = figure.axes[0].title.get_window_extent(canvas.get_renderer())
    assert bounds.x0 >= 0
    assert bounds.x1 <= figure.bbox.width
