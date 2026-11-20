import pytest

from tools.pipeline_eval.qualification.linear_gate_audit import eligibility, field, half_width


def test_decodes_only_the_bound_sibling_pair_in_the_numerical_archive():
    raw = b'[["fallback",0],["linear_paired_valid",false],["fallback","curved_pair"]]'
    assert field(raw, "linear_paired_valid", "fallback") is False
    with pytest.raises(ValueError, match="ambiguous"):
        field(raw + raw, "linear_paired_valid", "fallback")
    with pytest.raises(ValueError, match="malformed"):
        field(raw, "linear_paired_valid", "missing")


def test_each_arm_is_tested_without_changing_the_paired_gate_or_region():
    def paired(rows, *, include_linear, half_width_km):
        assert include_linear and half_width_km == 12.5
        return all(rows.values())

    assert eligibility({"c0": True, "fitted_c": False}, 12.5, paired) == (True, False, False)
    assert eligibility({"c0": False, "fitted_c": True}, 12.5, paired) == (False, True, False)
    with pytest.raises(ValueError, match="both calibration"):
        eligibility({"c0": True}, 12.5, paired)


def test_reads_the_offered_width_from_the_original_policy_header():
    raw = (
        b'[["box_width_km",12],["history_policy",["map",[['
        b'"box_width_km",["float","0x1.4000000000000p+5"]],["start_east_north_km",[]]]]]]'
    )
    assert half_width(raw, None) == 20.0
    with pytest.raises(ValueError, match="tile width"):
        half_width(raw.replace(b'0x1.4000000000000p+5', b'-0x1.4p+5'), None)


def test_a_gate_with_cross_arm_dependence_cannot_be_used_as_a_shortcut():
    def equal(rows, **kwargs):
        return rows["c0"] == rows["fitted_c"]

    with pytest.raises(ValueError, match="more than per-arm"):
        eligibility({"c0": 1, "fitted_c": 2}, 12.5, equal)
