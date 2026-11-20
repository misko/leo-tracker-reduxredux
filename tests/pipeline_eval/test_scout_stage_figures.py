import json
import re
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import scout_stage_figures as figures


def test_stage_inputs_are_hash_checked_before_use(tmp_path):
    measurement = tmp_path / "qualification.json"
    measurement.write_text('{"cases": ["A"]}')
    lock = tmp_path / "rules.json"
    lock.write_text(json.dumps({"files": {measurement.name: figures.sha(measurement)}}))
    assert figures.verify(tmp_path, lock.name) == (lock, measurement)
    measurement.write_text('{"cases": ["B"]}')
    with pytest.raises(ValueError, match="sealed stage evidence changed"):
        figures.verify(tmp_path, lock.name)


def test_capture_fft_measurement_keeps_the_two_producer_rosters_separate():
    measured = figures.capture_fft_data(figures.SUPPORT / "capture-fft")
    assert set(measured) == {"DS26-0036", "DS29-0174"}
    assert all(row["visits"] == 4 for row in measured.values())
    assert all(
        row["calls"] == row["scheduled_calls"] == row["exact"] == 8 for row in measured.values()
    )
    early, screened = (measured[k] for k in ("DS26-0036", "DS29-0174"))
    assert early["coarse"][1] < early["coarse"][0]
    assert screened["coarse"][1] > screened["coarse"][0]
    assert screened["warm_calls"] == 4
    assert screened["warm_total"][1] > screened["warm_total"][0]


def test_reproducible_chart_book_binds_every_page_to_its_sources(tmp_path):
    manifest = figures.render(tmp_path)
    pdf = (tmp_path / manifest["book"]).read_bytes()
    assert pdf.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page\b", pdf)) == len(manifest["pages"]) == 8
    assert [p["id"] for p in manifest["pages"]] == [
        "folded-bank",
        "capture-fft",
        "thinned-capture",
        "phase-scout",
        "phase-scout-coherent",
        "scout-budget",
        "scout-radius",
        "fractional-runtime",
    ]
    assert manifest["book_sha256"] == figures.sha(tmp_path / manifest["book"])
    index = (tmp_path / "README.md").read_text()
    for i, page in enumerate(manifest["pages"], 1):
        assert case_path(tmp_path, page["image"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert page["pdf_page"] == i
        assert f"({page['image']})" in index
        assert page["sources"] and all(
            figures.sha(figures.ROOT / file) == digest for file, digest in page["sources"].items()
        )


def case_path(folder, image):
    assert Path(image).name == image
    return folder / image


def test_coherent_page_shows_its_own_measured_counts():
    chart = figures.coherent_phase(figures.SUPPORT)
    try:
        labels = {text.get_text() for text in chart.figure.axes[0].texts}
        assert {"0/512", "77/192"} <= labels
        assert any(path.name == "coherent-lock.json" for path in chart.sources)
    finally:
        figures.plt.close(chart.figure)
