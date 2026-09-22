"""Phase figures remain available when science checks abstain."""

from io import BytesIO

from PIL import Image

from leo.presentation.adaptive_relative_phase import render_relative_phase


def test_unavailable_phase_has_two_legible_png_artifacts():
    images = render_relative_phase([], session_id="test", total_visits=20, applicable=False)
    assert set(images) == {"relative-phase-overview", "relative-phase-dwells"}
    for data in images.values():
        with Image.open(BytesIO(data)) as image:
            assert image.format == "PNG"
            assert image.width >= 1000 and image.height >= 800
