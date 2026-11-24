"""Exercise distinct-process census and the two published speed gates."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
import raw_denominator_audit as audit


def test_repeated_citations_are_deduplicated_by_process_identity():
    rows = audit.observations(audit.MEASUREMENTS)
    assert len(rows) == 17
    assert sum(len(row["sources"]) - 1 for row in rows) == 4
    assert sum(row["case"] == audit.POSITIVE and row["stratum"] == audit.PRIVATE for row in rows) == 3
    assert sum(row["case"] == audit.WITHHOLD and row["stratum"] == audit.PRIVATE for row in rows) == 6


def test_conflicting_same_process_citation_is_rejected(monkeypatch):
    original = audit.read

    def changed(measurements, name):
        doc, pin, path = original(measurements, name)
        if name == "combined-successor-original":
            doc["cases"][audit.POSITIVE]["installed"]["elapsed_s"] += 0.1
        return doc, pin, path

    monkeypatch.setattr(audit, "read", changed)
    with pytest.raises(ValueError, match="Conflicting duplicate stock process"):
        audit.observations(audit.MEASUREMENTS)


def test_two_case_gate_reciprocates_the_median_paired_ratio():
    combinations = [(10.0, 2.0), (12.0, 2.0)]
    analysis = audit.measure_sensitivity(combinations, {"candidate": (7.0, 0.5)})
    row = analysis["scores"]["candidate"]
    assert row["reciprocal_median"][0] == pytest.approx(2 / (7 / 10 + 0.5 / 2))
    assert row["gates"]["2.0"] == dict(summed=0, reciprocal_median=2, both=0)
    assert analysis["summed_candidate_budget_s"]["2.0"] == [6.0, 7.0]
