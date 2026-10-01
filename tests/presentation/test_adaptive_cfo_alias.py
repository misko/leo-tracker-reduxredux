import io

import numpy as np
from PIL import Image

from leo.analysis.starlink import CFO_ALIAS_SPACING_HZ
from leo.presentation.adaptive_cfo_alias import (
    alias_context_rows,
    render_adaptive_cfo_alias_context,
)
from tests.presentation.adaptive_overview_fixtures import overview_fixture


def test_alias_context_is_one_period_and_clipped_without_changing_originals():
    half = CFO_ALIAS_SPACING_HZ / 2
    rows = np.array([[3, 0, 199, -half + 5], [3, 0, 200, half - 5], [3, 1, 201, 0.0]])
    original = rows.copy()
    below, above = alias_context_rows(rows)
    np.testing.assert_array_equal(rows, original)
    assert len(below) == len(above) == 1
    np.testing.assert_array_equal(below[0, :3], rows[1, :3])
    np.testing.assert_array_equal(above[0, :3], rows[0, :3])
    assert below[0, 3] == rows[1, 3] - CFO_ALIAS_SPACING_HZ
    assert above[0, 3] == rows[0, 3] + CFO_ALIAS_SPACING_HZ
    for empty in alias_context_rows(np.empty((0, 4))):
        assert empty.shape == (0, 4)


def test_companion_pngs_preserve_source_metadata(monkeypatch):
    binding, manifest, products = overview_fixture(monkeypatch, count=12)
    images = render_adaptive_cfo_alias_context(binding, manifest, iter(products))
    assert set(images) == {"cfo-alias-context", "ch4-wrap-zoom"}
    for payload in images.values():
        with Image.open(io.BytesIO(payload)) as image:
            assert image.info["Session"] == binding.session_id
            assert image.width == 2480
            image.verify()
