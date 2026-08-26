from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports/2026_08_26_doppler_rate_experiment_campaign.md"


def test_campaign_report_links_resolve_and_uses_plain_png_figures() -> None:
    text = REPORT.read_text(encoding="utf-8")
    targets = re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", text)

    assert targets
    assert all(not target.startswith(("http://", "https://", "#")) for target in targets)
    assert all((REPORT.parent / target).is_file() for target in targets)

    figure_targets = re.findall(r"!\[[^]]*\]\(([^)]+)\)", text)
    assert len(figure_targets) == 5
    assert all(target.endswith(".png") for target in figure_targets)


def test_campaign_report_preserves_gates_and_error_semantics() -> None:
    text = REPORT.read_text(encoding="utf-8")

    required = (
        "only 4/15 captures passed",
        "scenario-equal nominal 95% coverage was only\n64.5%",
        "candidate/fixed-500 RMS 1.054 / 2.674 / 4.636",
        "only 3/20 common anchors",
        "post-freeze diagnostic",
        "required even likelihood surfaces/features absent",
        "known-truth rate error (Hz/s)",
        "no PRE-FIX recording",
        "no ongoing or newly\ncollected data",
    )
    assert all(phrase in text for phrase in required)

    assert "score the current unopened holdout" in text
    assert "**not authorized**" in text
