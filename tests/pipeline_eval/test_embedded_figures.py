from collections import Counter
from statistics import median
from zipfile import ZipFile

import pytest

from tools.pipeline_eval.qualification import embedded_figures as embedded
from tools.pipeline_eval.scoring import ROLES

DS26 = {
    "DS26-0036",
    "DS26-0070",
    "DS26-0112",
    "DS26-0122",
    "DS26-0203",
    "DS26-0209",
    "DS26-0277",
    "DS26-0311",
}
PUBLISHED_MEDIANS = {
    "c0": (3.42, 4.27, 4.90, 5.02, 1.87, 2.48, 5.13, 4.50, None, 3.25),
    "fitted_c": (3.40, 4.36, 4.90, 5.02, 1.86, 2.35, 5.13, 4.62, None, 3.25),
}


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_charts_cover_the_exact_embedded_scans_and_reproduce_the_published_medians(arm):
    pages = embedded.pages(arm, [])
    assert [page.name for page in pages] == list(embedded.TITLES)
    for page, expected in zip(pages, PUBLISHED_MEDIANS[arm], strict=True):
        assert page.method == page.name
        assert Counter((r.dataset, r.recording, r.series) for r in page.rows) == {
            ("DS26", case, series): 1 for case in DS26 for series in (*ROLES, "one")
        }
        outputs = [r for r in page.rows if r.series == "one"]
        if expected is None:
            assert page.name == "early_events"
            assert all(r.decision == "withheld" and r.error_km is None for r in outputs)
        else:
            assert all(r.decision == "published" for r in outputs)
            assert median(r.error_km for r in outputs) == pytest.approx(expected, abs=0.005)
        original = next(
            r for r in page.rows if r.series == "omitted-tracks" and r.recording == "DS26-0277"
        )
        assert original.decision == "timed_out"
        assert original.error_km is None
    forecast = next(page for page in pages if page.name == "early_stationary")
    assert "zero current-scan radio samples" in forecast.subtitle


@pytest.mark.parametrize(
    ("changed", "old", "new", "problem"),
    [
        ("01_stream/result.json", b"Streaming", b"Changed", "published source digest"),
        (
            "scores.csv",
            b"2.765917655703339",
            b"3.765917655703339",
            "coordinate-derived error differs",
        ),
    ],
)
def test_charts_reject_changed_primary_inputs_even_for_an_unselected_arm(
    tmp_path, changed, old, new, problem
):
    with (
        ZipFile(embedded.REPORT / embedded.ARCHIVE) as original,
        ZipFile(tmp_path / embedded.ARCHIVE, "w") as tampered,
    ):
        for name in original.namelist():
            data = original.read(name)
            if name == changed:
                assert old in data
                data = data.replace(old, new, 1)
            tampered.writestr(name, data)
    with pytest.raises(ValueError, match=problem):
        embedded.pages("fitted_c", ["early_stream"], tmp_path)
