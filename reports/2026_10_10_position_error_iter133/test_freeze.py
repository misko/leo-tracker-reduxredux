import pytest
from freeze import admit_receipts, verify_original_membership


@pytest.mark.parametrize("ids", [["a", "c"], ["a", "a"], ["a"], ["a", "b", "c"]])
def test_replay_cannot_substitute_or_drop_original_observations(ids):
    with pytest.raises(ValueError):
        verify_original_membership([dict(window_id=x) for x in ids], dict(window_ids=["a", "b"]))


def test_full_replay_retains_original_membership():
    verify_original_membership(
        [dict(window_id="b"), dict(window_id="a")], dict(window_ids=["a", "b"])
    )


def test_terminal_failed_member_is_not_excluded():
    parity = dict(label="a", status="failed")
    iq = dict(
        label="a",
        status="complete-with-failures",
        rows=2,
        expected=2,
        coverage_complete=True,
        counts={"complete": 1, "budget-exhausted": 1},
    )
    rows = [dict(window_id="x", status="complete"), dict(window_id="y", status="budget-exhausted")]
    assert admit_receipts("a", parity, iq, rows)["observations"] == 2


@pytest.mark.parametrize("fault", ["duplicate", "missing", "foreign", "counts", "false-success"])
def test_inconsistent_coverage_blocks_freeze(fault):
    parity = dict(label="a", status="complete")
    iq = dict(
        label="a",
        status="complete-with-failures",
        rows=2,
        expected=2,
        coverage_complete=True,
        counts={"complete": 1, "budget-exhausted": 1},
    )
    rows = [dict(window_id="x", status="complete"), dict(window_id="y", status="budget-exhausted")]
    if fault == "duplicate":
        rows[1]["window_id"] = "x"
    if fault == "missing":
        rows.pop()
    if fault == "foreign":
        parity["label"] = "b"
    if fault == "counts":
        iq["counts"] = {"complete": 2}
    if fault == "false-success":
        iq["status"] = "complete"
    with pytest.raises(ValueError):
        admit_receipts("a", parity, iq, rows)
