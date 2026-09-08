"""Scientific publication checks for the standalone Doppler paper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "doppler_paper", ROOT / "tools/report_starlink_doppler_paper.py"
)
assert SPEC is not None and SPEC.loader is not None
PAPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAPER)


@pytest.fixture(scope="module")
def data():
    return PAPER.load_data()


def test_paper_includes_full_cohort_and_actual_selected_trajectories(data):
    scans = data["scans"]
    assert len(scans) == 24
    assert sum(len(s["episodes"]) for s in scans) == 502
    assert sum(s["inventory"]["visit_count"] for s in scans) == 57288
    for rate in (2500000, 5000000):
        assert sum(s["inventory"]["sample_rate_hz"] == rate for s in scans) == 12
    assert {r["edge"] for r in data["pair"]} == {"lower", "upper"}
    assert all(len(r["t_s"]) == len(r["y_hz"]) > 6 for r in data["pair"])
    assert len(data["last"]["episodes"]) == 36


def test_evaluation_preserves_distinct_assistance_references_and_failures(data):
    m = data["metrics"]
    h = m["headline"]
    assert h["conditional_association_uses_known_site"]
    assert not h["same_evaluation_reference"]
    assert PAPER.separation(h["earlier_site_preset"], data["evaluation"]["truth"]) == pytest.approx(
        1290.2731876775
    )
    assert PAPER.separation(data["final"], data["evaluation"]["truth"]) == pytest.approx(
        1805.0144590960
    )
    assert sum(r["horizontal_error_m"] > 1e6 for r in m["continental_stages"]) == 3
    for size in (100, 500, 1000, 2000, 5000):
        nominal, corrected = [
            next(
                r
                for r in m["regional_unknown_height"]
                if r["region_km"] == size and r["fit_orbit_time"] == t
            )
            for t in (False, True)
        ]
        assert corrected["horizontal_error_m"] > nominal["horizontal_error_m"]
        assert corrected["heldout_rms_hz"] < nominal["heldout_rms_hz"]


def test_publication_hashes_figures_and_source_files(data):
    out = ROOT / PAPER.OUTPUT
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["inputs"] == data["inputs"]
    assert manifest["report_sha256"] == PAPER.sha(ROOT / PAPER.REPORT)
    assert manifest["generator_sha256"] == PAPER.sha(
        ROOT / "tools/report_starlink_doppler_paper.py"
    )
    assert set(manifest["outputs"]) == {*PAPER.FIGURES, "data-summary.json"}
    for path, digest in manifest["inputs"].items():
        assert PAPER.sha(ROOT / path) == digest
    for path, digest in manifest["outputs"].items():
        assert PAPER.sha(out / path) == digest
    for name in PAPER.FIGURES:
        with Image.open(out / name) as image:
            assert image.format == "PNG"
            assert image.width >= 1000 and image.height >= 500
            image.verify()


def test_publication_summary_matches_source_measurements(data):
    summary = json.loads((ROOT / PAPER.OUTPUT / "data-summary.json").read_text())
    assert summary["headline"] == data["metrics"]["headline"]
    assert summary["continental_position"] == data["final"]
    assert summary["continental_searches"] == data["metrics"]["continental_stages"]
    assert summary["figure3_tracklet_ids"] == [r["tracklet_id"] for r in data["pair"]]
    assert len(data["evaluation"]["runs"]) + len(data["evaluation"]["polishes"]) == 42
