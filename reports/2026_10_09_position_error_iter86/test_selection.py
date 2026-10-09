import pytest

from selection import selected_receipt, source_for


def test_fixed_selection_ignores_errors_and_does_not_fallback_to_contaminated_original():
    plan = dict(retry_members=["DS18-016", "DS18-017"],
                original_protocol_sha256="old", retry_protocol_sha256="new")
    member = dict(inventory_label="DS18-016")
    old = dict(member=member, protocol_sha256="old", status="complete", error_km=0)
    retry = dict(member=member, protocol_sha256="new", status="failed", error_km=100)
    assert selected_receipt("DS18-016", member, plan, old, retry)["status"] == "failed"
    assert selected_receipt("DS18-016", member, plan, old, None)["status"] == "pending"
    assert source_for("DS18-018", plan["retry_members"]) == "original84"
    with pytest.raises(AssertionError):
        selected_receipt("DS18-016", member, plan, old, old)


def test_complete_membership_has_exactly_two_retries():
    labels = [f"{ds}-{i:03d}" for ds, n in [("DS16", 63), ("DS17", 51), ("DS18", 34)]
              for i in range(1, n + 1)]
    assert len(labels) == len(set(labels)) == 148
    assert sum(source_for(label, ["DS18-016", "DS18-017"]) == "retry86" for label in labels) == 2
