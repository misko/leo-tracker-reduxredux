import copy

import pytest
from report import collect


def phases():
    result = {
        "search": dict(status="complete", protocol_sha256="digest", label="DS16-020", elapsed_s=3)
    }
    for branch in ("native", "fixed"):
        result[branch] = dict(
            status="complete",
            protocol_sha256="digest",
            label="DS16-020",
            branch=branch,
            fallback_available=False,
            elapsed_s=2,
            operational={
                a: dict(fit=dict(converged=True), branch=branch) for a in ("fitted-c", "zero-c")
            },
        )
    return result


def test_sealed_gate_precedes_all_evaluation():
    rows = phases()
    rows["fixed"]["status"] = "pending"
    with pytest.raises(ValueError, match="complete"):
        collect({}, "digest", rows.__getitem__, lambda _: pytest.fail("reference access"))
    rows = phases()
    rows["fixed"]["operational"]["zero-c"]["fit"]["converged"] = False
    with pytest.raises(ValueError, match="unqualified"):
        collect({}, "digest", rows.__getitem__, lambda _: pytest.fail("reference access"))


def test_matched_arms_delta_and_added_attempt_cost_preserved():
    rows = phases()
    before = copy.deepcopy(rows)
    calls = []

    def evaluate(operation):
        calls.append(operation["branch"])
        return dict(error_km=1 if operation["branch"] == "native" else 2)

    result = collect(
        dict(members=[dict(membership=dict(session_id="session"), exposure="consumed")]),
        "digest",
        rows.__getitem__,
        evaluate,
    )
    assert len(calls) == 4 and rows == before
    assert result["total_actual_elapsed_s"] == 7
    assert result["original129_failure_preserved"] and not result["independent_validation"]
    assert result["arms"]["zero-c"]["delta_km"] == 1
