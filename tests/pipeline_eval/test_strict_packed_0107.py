from copy import deepcopy

from reports.ALGO08.v3.strict_packed_0107 import complete_reader, signed_schedule


def test_both_short_radios_follow_original_sample_counter_at_anchored_cadence():
    rows = [dict(acquisition={"sample_start": 20*index}, sequence=index) for index in range(10)]
    original_visits = tuple(range(4)) + tuple(range(5, 10))
    probes = [dict(visit_index=visit, channel=1, edge="upper", actual_rf_hz=10940312500,
                   valid_start_counter=20*sequence, receiver_id=radio)
              for visit, sequence in enumerate(original_visits) for radio in (0, 1)]
    output = signed_schedule(probes, rows)
    assert set(output) == {str(visit) for visit in original_visits}
    assert [seq for seq, mode in output.items() if mode == "full"] == ["0", "9"]


def test_a_real_withhold_cannot_hide_a_missing_encoded_tail_or_native_aperture():
    expected = {"0": "full", "2": "short_primary"}
    build = {"original": {"window_count": 3, "uncompressed_sha256": "original"}, "binding": {"seek_sha256": "seal"},
             "checked_derivative": {"payload_bytes": 105}}
    row = dict(state="strict-packed-eight", loads=expected, encoded_blocks=6, seek_sha256="seal",
               original_decoded_sha256="original", checks=dict(payload_bytes=105, full_checks=1, frames=3, decoded_bytes=2240000))
    audit = dict(strict_packed_eight=True, original_windows=0, fallback=None, mapped_members=1, members=[row])
    assert complete_reader(audit, build, expected)
    for invalid in ({"encoded_blocks": 5}, {"loads": {"0": "full"}}):
        wrong = deepcopy(audit)
        wrong["members"][0].update(invalid)
        assert not complete_reader(wrong, build, expected)
