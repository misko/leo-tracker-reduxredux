from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "hours,label",
    [
        (-0.01, "After capture"),
        (0, "0–3 h"),
        (2.999, "0–3 h"),
        (3, "3–6 h"),
        (6, "6–12 h"),
        (12, "12–24 h"),
        (24, "24–48 h"),
        (48, "48–72 h"),
        (72, "≥72 h"),
    ],
)
def test_age_bins_preserve_future_epochs_and_exact_boundaries(monkeypatch, hours, label):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from report_association_orbit_age import bin_age

    assert bin_age(hours) == label
