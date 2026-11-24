from contextlib import contextmanager

import pytest

from reports.ALGO08.v3 import exact_named_cairo
from reports.ALGO08.v3.exact_named_cairo_media import act


def test_composition_uses_original_layout_for_other_products(monkeypatch):
    import direct_orbit_entry
    import direct_residual_entry

    packet, original = object(), object()
    active, audit = [], {}

    @contextmanager
    def orbit(renderer, counts):
        assert renderer is original
        active.append(renderer)
        yield
        assert active.pop() is renderer
        counts["native_orbit_figures"] = 4

    def residual(renderer, received, *, explicit_layout, title):
        assert active == [original] and renderer is original and received is packet
        assert not explicit_layout and title == "original"
        return {"position": b"original"}, {"native_residual_figures": 2}

    monkeypatch.setattr(direct_orbit_entry, "native_orbits", orbit)
    monkeypatch.setattr(direct_residual_entry, "render", residual)
    assert exact_named_cairo.draw_cairo(original, packet, audit, title="original") == {"position": b"original"}
    assert not active
    act(audit["work"])


@pytest.mark.parametrize("counts", [
    {"native_orbit_figures": 4},
    {"native_orbit_figures": 4, "native_residual_figures": 2, "native_orbit_fallback": "unsupported"},
])
def test_incomplete_or_fallback_renderer_cannot_qualify(counts):
    with pytest.raises(ValueError, match="all six native sheets"):
        act(counts)
