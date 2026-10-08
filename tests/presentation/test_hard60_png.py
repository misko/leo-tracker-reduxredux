import struct

from leo.presentation.regional_position import regional_position_figure, render_regional_position
from tests.contracts.test_regional_position_v2 import document


def test_hard60_png_dimensions_label_and_explicit_insufficient_evidence():
    doc = document()
    figure = regional_position_figure(doc, "V16")
    assert "Hard60 / V16" in figure._suptitle.get_text()
    assert "unavailable" in figure.axes[0].get_title()
    png = render_regional_position(doc, "V16")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24]) == (1080, 960)


def test_recovery_png_identifies_new_analysis_and_keeps_standard_dimensions():
    doc = document().model_copy(
        update={"diagnostics": {"recovery": {"attempted_points": 12, "converged_points": 10}}}
    )
    figure = regional_position_figure(doc, "V16")
    assert "Timing recovery: 10/12" in figure._supxlabel.get_text()
    png = render_regional_position(doc, "V16")
    assert struct.unpack(">II", png[16:24]) == (1080, 960)
