import json

import pytest
from report_parity import summarize


def test_full_membership_partial_arm_and_pending_preserved():
    members = [dict(label="DS16-001", membership={}), dict(label="DS17-001", membership={})]
    receipts = {
        "DS16-001": dict(
            label="DS16-001",
            status="failed",
            optimizer_calls=0,
            endpoint_evaluations=2,
            elapsed_s=3,
            arms={
                "fitted-c": dict(status="complete", delta=0),
                "zero-c": dict(status="failed", error="saved mismatch"),
            },
        )
    }
    result = summarize(members, receipts)
    assert result["groups"]["all"]["statuses"] == {"failed": 1, "pending": 1}
    assert result["groups"]["all"]["arms"]["fitted-c"]["complete"] == 1
    assert not result["full_parity_verified"]
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="unknown"):
        summarize(members, {"wrong": {}})


def test_complete_requires_real_two_arm_parity():
    members = [dict(label="POST18-001", membership={})]
    row = dict(
        label="POST18-001",
        status="complete",
        optimizer_calls=0,
        endpoint_evaluations=2,
        arms={
            a: dict(status="complete", stored=1, reconstructed=1, delta=0)
            for a in ("fitted-c", "zero-c")
        },
    )
    result = summarize(members, {"POST18-001": row})
    assert result["full_parity_verified"]
    assert "newer development" in result["groups"]
    row["arms"]["zero-c"]["delta"] = 0.01
    with pytest.raises(ValueError, match="tolerance"):
        summarize(members, {"POST18-001": row})
    row["arms"]["zero-c"]["delta"] = 0
    row["endpoint_evaluations"] = 1
    with pytest.raises(ValueError, match="two evaluations"):
        summarize(members, {"POST18-001": row})
