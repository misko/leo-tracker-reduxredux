from io import BytesIO

from PIL import Image

from leo.cli.blind_regional import evaluated_document
from leo.presentation.blind_regional import render_blind_regional
from tests.cli.test_blind_regional_cli import prepared_and_result
from tests.storage.test_blind_regional_store import document


def test_blind_pngs_render_diagnostic_and_explicit_insufficiency():
    prepared, result = prepared_and_result()
    for evidence in (evaluated_document(prepared, result, runtime_ms=1), document()):
        images = render_blind_regional(evidence)
        assert tuple(images) == ("blind-association", "blind-position", "blind-position-modes")
        for payload in images.values():
            with Image.open(BytesIO(payload)) as image:
                image.load()
                assert image.format == "PNG"
                assert image.width > 1000 and image.height > 700
