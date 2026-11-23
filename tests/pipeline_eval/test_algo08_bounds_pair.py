from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def pair(monkeypatch):
    report = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(report))
    return import_module("triage_bounds")


def test_detector_provenance_does_not_hide_scientific_differences(pair):
    native = {"source": {"probes": ["a", "b"], "analysis_manifest_sha256": "original"},
              "provenance": {"detector_sha256": "original", "run_id": "a", "scope": "all"}}
    rebuilt = native | {
        "source": native["source"] | {"analysis_manifest_sha256": "rebuilt"},
        "provenance": native["provenance"] | {"detector_sha256": "rebuilt", "run_id": "b"},
    }
    terminal = {"native_sha256": "original native", "arms": {"fitted_c": [1, 2]}}
    rebound = terminal | {"native_sha256": "rebuilt native"}
    baseline = {"probe_sha256": "equal", "pngs": {"position": "original", "track-rms": "one"},
                "png_pixels": {"position": {"rgba_sha256": "same decoded pixels"}}}
    contender = {"probe_sha256": "equal", "pngs": {"position": "rebuilt", "ch1-4-all": "two"},
                 "png_pixels": {"position": {"rgba_sha256": "same decoded pixels"}}}

    comparison = pair.pair_comparison([baseline, contender], [native, rebuilt], [terminal, rebound])
    assert comparison["ordered_probes"] and comparison["detection_without_detector_identity"]
    assert comparison["terminal_without_detection_digest"] and not comparison["terminal_document"]
    assert not comparison["detection_document"]
    assert comparison["pngs"] == {"position": False, "track-rms": False, "ch1-4-all": False}
    assert comparison["png_pixels"] == {"position": True}

    rebuilt["source"] = {"probes": ["b", "a"]}
    rebound["arms"] = {"fitted_c": [2, 1]}
    changed = pair.pair_comparison([baseline, contender], [native, rebuilt], [terminal, rebound])
    assert not changed["ordered_probes"] and not changed["detection_without_detector_identity"]
    assert not changed["terminal_without_detection_digest"]


def test_pin_blocks_a_changed_archive_or_region(pair, monkeypatch, tmp_path):
    args = SimpleNamespace(archive=tmp_path, region=tmp_path / "region.json")
    monkeypatch.setattr(pair.paired_publication, "archive_identity", lambda _: {"pin": "changed"})
    with pytest.raises(ValueError, match="archive changed"):
        pair.check_assignment(args, {"archive": {"pin": "original"}})

    args.region.write_text("changed")
    with pytest.raises(ValueError, match="Benchmark input pin changed"):
        pair.check_assignment(args, {"archive": {"pin": "changed"}})


def test_calibration_keeps_fit_and_horizontal_error_separate(pair, monkeypatch):
    audit = {"cases": [dict(dataset_label=pair.CASE, sealed_metadata_digests_verified=True,
                            authority_eligible=True, reference={"latitude_deg": 0., "longitude_deg": 0.},
                            authority_revision="test", evidence="survey")]}
    monkeypatch.setattr(pair, "checked", lambda *args: json.dumps(audit).encode())
    arms = {"c0": {"latlon": [0., 0.], "rf_rms_hz": 2.}, "fitted_c": {"latlon": [1., 0.], "rf_rms_hz": 1.}}
    result = pair.calibration_comparison({"baseline": {"arms": arms}})["runs"]["baseline"]
    assert result["fitted_minus_c0_rf_rms_hz"] == -1.
    assert result["fitted_minus_c0_horizontal_error_km"] == pytest.approx(111.195, abs=.001)


@pytest.mark.parametrize("field, wrong", [("cached_pages", 242127), ("observed_members", 12),
                                         ("observed_file_pages", 242127), ("unavailable", {"EPERM": 1})])
def test_weak_pair_requires_full_coverage_and_full_cache(pair, field, wrong):
    complete = dict(members=13, observed_members=13, observed_file_pages=242128, cached_pages=242128, unavailable={})
    pair.require_full_cache(complete)
    with pytest.raises(ValueError, match="not fully cached"):
        pair.require_full_cache(complete | {field: wrong})
