"""Publication checks keep conditional benchmarks separate from blind localization."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "continental_synthesis", ROOT / "tools/report_continental_positioning_synthesis.py"
)
assert SPEC is not None and SPEC.loader is not None
REPORT_TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT_TOOL)


def test_headline_preserves_different_assumptions_and_evaluation_references():
    metrics = REPORT_TOOL.load_metrics()
    headline = metrics["headline"]
    assert headline["conditional_association_uses_known_site"]
    assert not headline["same_accuracy_population"]
    assert not headline["same_evaluation_reference"]
    assert headline["reference_coordinate_separation_m"] == pytest.approx(1290.2731876775)
    assert round(headline["continental_unknown_position_m"] / 1000, 1) == 1.8
    assert round(headline["conditional_three_scan_m"] / 1000, 1) == 1.2
    assert all(row["horizontal_error_m"] > 1200 for row in metrics["regional_unknown_height"])


def test_report_retains_failed_searches_and_adverse_model_ablation():
    metrics = REPORT_TOOL.load_metrics()
    stages = metrics["continental_stages"]
    assert len(stages) == 6
    assert sum(row["horizontal_error_m"] > 1_000_000 for row in stages) == 3
    assert len(metrics["wrong_time_controls"]) == 2
    rows = metrics["regional_unknown_height"]
    for size in {row["region_km"] for row in rows}:
        fixed, corrected = [
            next(
                row for row in rows if row["region_km"] == size and row["fit_orbit_time"] == timing
            )
            for timing in (False, True)
        ]
        assert corrected["heldout_rms_hz"] < fixed["heldout_rms_hz"]
        assert corrected["horizontal_error_m"] > fixed["horizontal_error_m"]


def test_sampling_arithmetic_is_separate_from_measured_precision():
    metrics = REPORT_TOOL.load_metrics()
    low, *_, high = metrics["sample_rate_theory"]
    assert high["ci16_two_rx_MB_s"] == 200
    assert high["integer_rounding_rms_ns"] * math.sqrt(12) == pytest.approx(40)
    assert high["one_sample_light_travel_m"] == pytest.approx(11.99169832)
    # Fractional timing can beat integer rounding; sample period is not a CRLB.
    measured = metrics["fractional_7fea_fits"]["log_score_parabola"]["residual_rms_us"] * 1000
    assert measured < low["integer_rounding_rms_ns"]


def test_published_manifest_matches_inputs_report_and_pngs():
    output = ROOT / REPORT_TOOL.OUTPUT
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["report_inventory_count"] == 148
    assert manifest["report_sha256"] == REPORT_TOOL.sha(ROOT / REPORT_TOOL.REPORT)
    assert manifest["generator_sha256"] == REPORT_TOOL.sha(Path(REPORT_TOOL.__file__))
    for group in ("numeric_inputs", "linked_pngs", "reports"):
        for path, expected in manifest[group].items():
            assert REPORT_TOOL.sha(ROOT / path) == expected, path
    for name, expected in manifest["outputs"].items():
        assert REPORT_TOOL.sha(output / name) == expected, name
    assert len(list(output.glob("*.png"))) == 5
    for path in manifest["linked_pngs"]:
        with Image.open(ROOT / path) as image:
            assert image.format == "PNG"
            assert image.width >= 1000 and image.height >= 500
            image.verify()


def test_every_reference_is_explicit_in_the_saved_headline_metrics():
    output = ROOT / REPORT_TOOL.OUTPUT
    published = json.loads((output / "metrics.json").read_text())
    assert published == REPORT_TOOL.load_metrics()
    assert (
        published["headline"]["earlier_site_preset"]["latitude_deg"]
        != (published["headline"]["continental_evaluation_reference"]["latitude_deg"])
    )
