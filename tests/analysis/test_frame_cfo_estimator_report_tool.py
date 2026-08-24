from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools import report_frame_cfo_estimator_study as report


def test_synthetic_frame_cfo_report_evidence_and_figures(tmp_path: Path) -> None:
    rows, step = report._synthetic_benchmark(5)

    assert len(rows) == 20
    assert {row["scenario"] for row in rows} == {
        "clean high SNR",
        "clean medium SNR",
        "clean low SNR",
        "15% symbol outliers",
        "one coherent tone spur",
    }
    spur = {row["method"]: row for row in rows if row["scenario"] == "one coherent tone spur"}
    assert spur["robust-profile"]["rmse_hz"] < spur["parabolic-profile"]["rmse_hz"]
    assert step["detection_fraction"] > step["false_alarm_fraction"]

    synthetic_path = tmp_path / "synthetic.png"
    design_path = tmp_path / "design.png"
    report._plot_synthetic(rows, step, synthetic_path)
    report._plot_design(design_path)
    for path in (synthetic_path, design_path):
        with Image.open(path) as image:
            image.verify()


def test_frozen_t01_t06_crosscheck_is_valid_json() -> None:
    path = (
        Path(__file__).parents[2]
        / "reports/figures/2026_08_24_frame_cfo_estimator_study/t01-t06-crosscheck.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["schema"] == "org.leo.research.frame-cfo-cohort-crosscheck/v1"
    assert [item["label"] for item in document["dwells"]] == ["T01", "T06"]
    assert all(item["qualified_frame_count"] > 70 for item in document["dwells"])
    assert all(
        item["tone_deletion_influence"]["over_gate_fraction"] == 0.0 for item in document["dwells"]
    )
    assert (
        max(item["tone_deletion_influence"]["maximum_spread_hz"] for item in document["dwells"])
        < 75.0
    )
