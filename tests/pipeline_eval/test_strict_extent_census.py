import pytest

from reports.ALGO08.v3.strict_extent_census import NOMINAL_BYTES, census


def test_member_extent_differences_survive_equal_recording_total():
    chunks = [{"window_count": 1, "uncompressed_bytes": NOMINAL_BYTES + delta} for delta in (-8, 8)]
    source = dict(window_count=2, recording_state="incomplete", raw_recording=dict(identity_sha256="abc", chunks=chunks))
    case = dict(content="abc", id="trial", windows=2, recording_state="incomplete")
    rows = [dict(method="compact_two_scan", case="trial", calibration=arm, fix="True") for arm in ("c0", "fitted_c")]
    result = census([source], [case], rows)
    assert result["non_nominal_chunks"] == 2
    assert result["affected"]["trial"]["nominal_minus_actual_bytes"] == 0
    assert result["historical_compact_fixes_both"] == 1
    with pytest.raises(ValueError, match="Incomplete compact"):
        census([source], [case], rows[:1])
    with pytest.raises(ValueError, match="Repeated outcome"):
        census([source], [case], rows + rows)
