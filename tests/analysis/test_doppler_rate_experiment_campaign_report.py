from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports/2026_08_26_doppler_rate_experiment_campaign.md"
REPORTS = ROOT / "reports"
LEDGER = ROOT / "docs/research/evidence-ledger.md"


def test_campaign_report_links_resolve_and_uses_plain_png_figures() -> None:
    text = REPORT.read_text(encoding="utf-8")
    targets = re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", text)

    assert targets
    assert all(not target.startswith(("http://", "https://", "#")) for target in targets)
    assert all((REPORT.parent / target).is_file() for target in targets)

    figure_targets = re.findall(r"!\[[^]]*\]\(([^)]+)\)", text)
    assert len(figure_targets) == 8
    assert all(target.endswith(".png") for target in figure_targets)


def test_campaign_report_preserves_gates_and_error_semantics() -> None:
    text = REPORT.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

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
        "5,413 targets = 5,245 eligible + one boundary\n+ 167 no-support + zero missing",
        "61.7473, 57.7538, 60.2889, and 58.1705 Hz",
        "equal-capture ratio was 0.9648629",
        "descriptive forecasting winner",
        "campaign-level calibrated-rate/interval result remains **ABSTAIN**",
        "association-evaluable captures | 8/10",
        "recovered response tracks | 8/8",
        "evaluable captures passing the wrong-time empirical-p gate | **0/8**",
        "captures passing the at-least-two stable rolling-origins gate | **1/8**",
        "full catalog-compatibility passes | **0/8**",
        "absolute secure NORAD identities | **0**",
    )
    assert all(phrase in text for phrase in required)

    qualifier = (
        "Upstream Standard source, alias, trajectory, and epoch selection may use "
        "all-Qin GLRT64 evidence. The result is therefore downstream-withheld and "
        "conditional on that frozen upstream conditioning, not an end-to-end unopened "
        "acquisition test."
    )
    assert qualifier in normalized
    assert "pending" not in text.lower()
    assert "**FAIL**, not a near-pass" in text


def test_evidence_ledger_indexes_the_complete_report_markdown_inventory() -> None:
    report_markdown = {path.resolve() for path in REPORTS.rglob("*.md")}
    top_level = {path for path in report_markdown if path.parent == REPORTS}
    post_refill_root = (REPORTS / "2026_08_25_post_refill_24h_retrospective").resolve()
    post_refill = {path for path in report_markdown if post_refill_root in path.parents}
    scanner_root = (REPORTS / "scanner-rendered-samples").resolve()
    scanner = {path for path in report_markdown if scanner_root in path.parents}
    tle_readme = {(REPORTS / "figures/2026_08_21_tle_doppler_alignment/README.md").resolve()}

    assert len(report_markdown) == 130
    assert len(top_level) == 119
    assert len(post_refill) == 7
    assert len(scanner) == 3
    assert tle_readme <= report_markdown
    assert top_level | post_refill | scanner | tle_readme == report_markdown

    text = LEDGER.read_text(encoding="utf-8")
    targets = re.findall(r"!?(?:\[[^]]*\])\(([^)#]+)(?:#[^)]+)?\)", text)
    linked_report_markdown = {
        resolved
        for target in targets
        if (resolved := (LEDGER.parent / target).resolve()).suffix == ".md"
        and REPORTS.resolve() in resolved.parents
    }
    assert linked_report_markdown == report_markdown
