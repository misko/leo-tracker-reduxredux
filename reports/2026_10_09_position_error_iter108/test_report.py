import copy
import runpy
from pathlib import Path

import pytest

summarize = runpy.run_path(str(Path(__file__).with_name("report.py")))["summarize"]


def fixture():
    member = dict(inventory_label="DS16-001", dataset="DS16")
    population = dict(
        rows=4,
        entropy_nats=dict(mean=2),
        confidence_below_half=1,
        confidence_half_to_nine_tenths=1,
        confidence_at_least_nine_tenths=2,
    )
    ambiguity = dict(
        populations=dict(all=population, linked=dict(rows=2)),
        switches=dict(
            links=1, changed=1, confident_satellite_switches=0, weak_or_clutter_switches=1
        ),
    )
    receipt = dict(
        member=member,
        protocol_sha256="hash",
        status="complete",
        arms={a: dict(ambiguity=copy.deepcopy(ambiguity)) for a in ("fitted-c", "zero-c")},
    )
    return dict(members=[dict(member=member)]), {"DS16-001": receipt}


def test_matched_descriptive_known_values():
    plan, receipts = fixture()
    result = summarize(plan, receipts, "hash")
    assert result["complete"]
    data = result["metrics"]["DS16"]
    assert data["fitted-c"] == data["zero-c"]
    assert data["zero-c"]["linked_fraction"] == 0.5
    assert data["zero-c"]["mean_entropy_nats"] == 2
    assert data["zero-c"]["confidence_fractions"]["confidence_below_half"] == 0.25


@pytest.mark.parametrize("status", ["missing", "failed"])
def test_incomplete_withholds_all_metrics(status):
    plan, receipts = fixture()
    if status == "missing":
        receipts.clear()
    else:
        receipts["DS16-001"].update(status="failed", error="synthetic failure")
    result = summarize(plan, receipts, "hash")
    assert result["metrics"] is None
    assert result["membership"][0]["status"] == status


def test_provenance_and_matched_arms_required():
    plan, receipts = fixture()
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "wrong hash")
    del receipts["DS16-001"]["arms"]["zero-c"]
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "hash")
