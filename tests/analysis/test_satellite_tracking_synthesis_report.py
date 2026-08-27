from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports" / "2026_08_27_satellite_tracking_association_and_pnt_synthesis.md"
ARTIFACT_ROOT = ROOT / "reports" / "figures" / "2026_08_27_satellite_tracking_synthesis"
EVIDENCE = ARTIFACT_ROOT / "satellite-tracking-synthesis-evidence.json"
TOOL = ROOT / "tools" / "report_satellite_tracking_synthesis.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("report_satellite_tracking_synthesis", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_synthesis_evidence_matches_sealed_results() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["schema"] == "leo.satellite-tracking-synthesis.v1"
    assert evidence["final_holdout_aggregate"] == {
        "capture_count": 10,
        "evaluable_count": 8,
        "recovered_count": 8,
        "catalog_compatible_count": 0,
        "secure_norad_count": 0,
        "gate_pass_counts": {
            "recovered_track": 8,
            "minimum_heldout_odd_bins": 8,
            "minimum_heldout_odd_bin_fraction": 8,
            "absolute_rank_one_heldout_odd_rms": 6,
            "primary_baseline_rank_one_agreement": 2,
            "training_runner_margin_ratio": 6,
            "heldout_rank_one_remains_best": 2,
            "heldout_runner_margin_ratio": 6,
            "permutation_empirical_p": 7,
            "at_least_2_rolling_origins_complete_and_stable": 1,
            "utc_site_predecessor_controls_complete_and_stable": 8,
        },
    }
    by_suffix = {row["suffix"]: row for row in evidence["final_holdout"]}
    assert by_suffix["022235"]["primary_norad"] == "60734"
    assert by_suffix["022235"]["future_best_norad"] == "67814"
    assert by_suffix["030000"]["primary_future_rms_hz"] == 136.831758653788
    assert by_suffix["033302"]["rolling_norads"] == [None, "60934", "60934"]
    assert by_suffix["034929"]["failure_reasons"] == [
        "insufficient_total_bins",
        "insufficient_training_bins",
    ]
    assert evidence["retrospective"]["recovered_count"] == 4
    assert evidence["retrospective"]["candidate_evidence_count"] == 0
    assert [row["norad_id"] for row in evidence["retrospective"]["primary_candidates"]] == [
        62124,
        66811,
        58029,
        59748,
    ]
    assert [row["main"]["training_winner"] for row in evidence["long_arcs"]] == [
        67930,
        59748,
    ]
    assert evidence["long_arcs"][0]["rolling_training_winners"] == [67930, 67930, 67930]
    assert evidence["long_arcs"][1]["rolling_training_winners"] == [65438, 59748, 59748]
    assert evidence["legacy"] == {
        "track_count": 37,
        "dwell_count": 13,
        "orbit_beats_line_count": 1,
        "wrong_time_pass_count": 3,
        "secure_count": 0,
    }
    assert evidence["claim_boundary"]["secure_norad_claimed"] is False
    assert evidence["claim_boundary"]["positioning_validation_claimed"] is False

    for relative, expected_digest in evidence["source_digests"].items():
        source = ROOT / relative
        actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual == expected_digest


def test_report_has_required_sections_and_all_local_links_resolve() -> None:
    text = REPORT.read_text(encoding="utf-8")
    for heading in (
        "## 1. Introduction and motivation",
        "## 3. Background and measurement model",
        "## 4. Data cohorts",
        "## 5. Methods",
        "## 6. Results",
        "## 7. Discussion",
        "## 8. Recommended next steps",
        "## 9. Conclusions",
        "## 10. Reproducibility and claim boundary",
    ):
        assert heading in text
    assert "Complete historical catalogue compatibility | **0/8**" in text
    assert "No tested dwell provides a secure satellite" in text

    links = re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", text)
    assert links
    for target in links:
        if "://" in target or target.startswith("#"):
            continue
        path = (REPORT.parent / target).resolve()
        assert path.exists(), target
        if path.suffix == ".png":
            with Image.open(path) as image:
                image.verify()


def test_renderer_reproduces_summary_and_valid_pngs(tmp_path: Path) -> None:
    module = _load_tool()
    rendered = module.render(tmp_path)

    committed = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert rendered == committed
    for name in (
        "final-holdout-gate-matrix.png",
        "final-holdout-identity-stability.png",
        "long-arc-wrong-epoch-specificity.png",
    ):
        with Image.open(tmp_path / name) as image:
            image.verify()
