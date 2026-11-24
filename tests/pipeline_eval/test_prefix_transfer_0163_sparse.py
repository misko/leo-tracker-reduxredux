import pytest

from reports.ALGO08.v3.prefix_transfer_0163_sparse import measured_rows


def lane(visit, antenna, candidates, *, channel=6):
    return {"visit_index": visit, "receiver_id": antenna, "channel": channel, "candidates": candidates}


def test_splices_all_rows_including_empties_then_only_restores_one_lane():
    original = [lane(4, 0, [3]), lane(61, 0, [8]), lane(61, 1, []), lane(64, 0, [22])]
    measured = [lane(4, 0, []), lane(61, 0, [9]), lane(61, 1, [13])]
    hybrid, restored = measured_rows(original, original[:3], measured)
    assert hybrid == measured + original[3:]
    assert restored == [measured[0], original[1], measured[2], original[3]]
    assert hybrid[-1] is restored[-1] is original[-1]


def test_rejects_missing_empty_lane_and_radio_relabeling():
    original = [lane(61, 0, [8]), lane(61, 1, [])]
    with pytest.raises(ValueError, match="lane metadata"):
        measured_rows(original, original, [lane(61, 0, [9])])
    with pytest.raises(ValueError, match="lane metadata"):
        measured_rows(original, original, [lane(61, 0, [9], channel=5), original[1]])


def test_original_installed_prefix_has_to_match_exactly():
    with pytest.raises(ValueError, match="installed factors"):
        measured_rows([lane(61, 0, [8])], [lane(61, 0, [12])], [lane(61, 0, [9])])


def test_only_a_changed_installed_singleton_can_be_restored():
    with pytest.raises(ValueError, match="actually changed"):
        measured_rows([lane(61, 0, [8])], [lane(61, 0, [8])], [lane(61, 0, [8])])
