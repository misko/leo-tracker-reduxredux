import pytest

from reports.ALGO08.v3.finalist_comparison_figure import PIN, elapsed
from reports.ALGO08.v3.first_use_native_budget import M
from reports.ALGO08.v3.legacy_frame_figure import load_seal


def test_plot_boundaries_match_signed_pair():
    data = load_seal(M/"legacy-first-map-finalist.json.gz", PIN)
    stock, previous, combined = elapsed(data)
    assert sum(stock)/sum(combined) == pytest.approx(1.471617, abs=1e-6)
    assert sum(previous)-sum(combined) == pytest.approx(.48731, abs=1e-5)
    with pytest.raises(ValueError):
        elapsed(dict(data, qualified=False))
