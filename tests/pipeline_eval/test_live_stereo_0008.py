import pytest

from reports.ALGO08.v3.live_stereo_0008 import compare_archive


@pytest.fixture
def signed_rows():
    rows = [dict(visit_index=visit, receiver_id=radio, valid_start_counter=3 + visit,
                 candidates=[{"fractional_tracking_cfo_hz": 7}] if radio == 0 else [])
            for visit in (3, 4, 6) for radio in (0, 1)]
    decisions = [(3, "full", True), (4, "short_primary", True), (6, "short_primary", False)]
    masked = [*rows[:4], *(dict(row, candidates=[]) for row in rows[4:])]
    return rows, masked, decisions


def test_mask_preserves_order_kept_factors_and_empty_stereo_rows(signed_rows):
    rows, masked, decisions = signed_rows
    audit = compare_archive(rows, masked, decisions)
    assert audit["omitted_visits"] == 1
    assert audit["reference_factors_by_mode"] == {"full": 1, "short_primary": 1, "skip": 1}


@pytest.mark.parametrize("mode", ("retained_factor", "omitted_counter", "missing_lane", "missing_decision", "anchor"))
def test_archive_audit_rejects_scope_and_scientific_changes(signed_rows, mode):
    rows, masked, decisions = signed_rows
    if mode == "retained_factor":
        masked[2] = dict(masked[2], candidates=[])
    elif mode == "omitted_counter":
        masked[-1] = dict(masked[-1], valid_start_counter=7)
    elif mode == "missing_lane":
        masked.pop()
    elif mode == "missing_decision":
        decisions.pop()
    else:
        decisions[0] = (3, "full", False)
    with pytest.raises(ValueError, match="frozen schedule|archived probes"):
        compare_archive(rows, masked, decisions)
