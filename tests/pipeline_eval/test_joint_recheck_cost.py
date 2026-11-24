from copy import deepcopy

import pytest

from reports.ALGO08.v3.joint_recheck_cost import additional_work, price, read


def test_both_scheduled_slots_require_full_positive_calls_and_only_preselection_saves_short():
    def clock(ms):
        return {"wall_ns": {"mean": ms * 1e6}}
    donor = {"full": {"positive": clock(4)}, "short_primary": {"empty": clock(1), "positive": clock(2)}}
    assert additional_work(3, 2, donor) == pytest.approx({"after_short_s": .020, "scheduled_instead_s": .013})


def test_receipts_require_same_field_packet_opportunities_and_disjoint_edits():
    publication = read("ds30-0049-joint-recovery")
    field = read("first30-empty-call-roof")
    case = next(c for c in field["cases"] if c["case"] == "DS30-0049")
    donors = field["late_pilot_donor_clocks"]
    result = price(publication, case, donors)
    assert result["short_lanes"] == 1622 and result["inserted"] + result["replaced"] == 176
    assert result["additional_reduction_needed_s"]["after_short_s"][0] > result["measured_s_over_half"]
    with pytest.raises(ValueError, match="different inputs"):
        price(publication, dict(case, native_sha256="unrelated"), donors)
    duplicate = deepcopy(publication)
    edits = duplicate["plan"]["change"]["edits"]
    edits[0]["observation_id"] = edits[1]["observation_id"]
    with pytest.raises(ValueError, match="disjoint"):
        price(duplicate, case, donors)
