from matplotlib.axes import Axes

from leo.presentation.adaptive_tle_position import render_adaptive_tle_position
from tests.contracts.test_adaptive_tle_position import document_v2, document_v3


def test_single_sacramento_panel_prints_error_and_legacy_still_renders(monkeypatch):
    titles = []
    original = Axes.set

    def record(self, **kwargs):
        if "title" in kwargs:
            titles.append(kwargs["title"])
        return original(self, **kwargs)

    monkeypatch.setattr(Axes, "set", record)
    assert render_adaptive_tle_position(document_v3()).startswith(b"\x89PNG")
    assert len(titles) == 1
    assert "Sacramento" in titles[0] and "reference error 1.23 km" in titles[0]
    titles.clear()
    assert render_adaptive_tle_position(document_v2()).startswith(b"\x89PNG")
    assert len(titles) == 2
