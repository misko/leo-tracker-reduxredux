from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports" / "2026_08_26_retrospective_satellite_nuisance_results.md"
EVIDENCE = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_26_retrospective_satellite_nuisance"
    / "retrospective-satellite-nuisance-evidence.json"
)


def test_report_claims_match_frozen_machine_evidence() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    aggregate = evidence["aggregate"]
    report = REPORT.read_text(encoding="utf-8")

    assert aggregate["baseline_recovered_track_count"] == 4
    assert aggregate["primary_recovered_track_count"] == 4
    assert aggregate["candidate_evidence_track_count"] == 0
    assert aggregate["secure_norad_count"] == 0
    assert aggregate["hierarchy_to_baseline_future_rms_ratio"] == 1.0147938258450722
    assert "`4 -> 4` recovered tracks" in report
    assert "**0 secure NORAD identities**" in report
    assert "1.48% worse" in report


def test_latest_causal_tle_sensitivity_is_exact_and_invisible_only() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    sensitivity = evidence["latest_causal_150802_tle_sensitivity"]

    assert sensitivity["visible_population_equal"] is True
    assert sensitivity["full_ranking_equal"] is True
    assert sensitivity["all_required_metrics_identical"] is True
    assert sensitivity["changed_catalogue_norad_ids"] == [47657]
    assert sensitivity["changed_visible_norad_ids"] == []
    assert sensitivity["winner_norad_id"] == 59748


def test_report_local_links_and_pngs_resolve() -> None:
    text = REPORT.read_text(encoding="utf-8")
    links = re.findall(r"\[[^]]+\]\(([^)]+)\)", text)
    assert links
    for target in links:
        if "://" in target:
            continue
        path = (REPORT.parent / target).resolve()
        assert path.exists(), target
        if path.suffix == ".png":
            with Image.open(path) as image:
                image.verify()
