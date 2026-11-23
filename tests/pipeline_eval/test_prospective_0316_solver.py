from hashlib import sha256

import pytest

from reports.ALGO08.v3 import prospective_0316_solver as replay


def test_owner_deltas_count_removed_added_remapped_and_role_only():
    before = [["a", 11, "predictive"], ["b", 12, "predictive"], ["c", 13, "core"], ["d", 14, "core"]]
    after = [["b", 15, "predictive"], ["c", 13, "predictive"], ["d", 14, "core"], ["e", 16, "core"]]
    result = replay.owner_delta(before, after)
    assert result["stock"] == result["candidate"] == 4
    assert result["shared"] == 3
    assert result["reassigned_norad"] == result["changed_roles"] == 1
    assert result["dropped"] == ["a"] and result["added"] == ["e"]
    assert result["changed"] == [["b", 12, "predictive", 15, "predictive"], ["c", 13, "core", 13, "predictive"]]


def test_owner_rows_reject_duplicates_and_distinguish_order():
    items = [["a", 11, "core"], ["b", 12, "core"]]
    assert replay.owner_delta(items, items)["identical_ordered_rows"]
    assert not replay.owner_delta(items, items[::-1])["identical_ordered_rows"]
    assert replay.owner_delta(items, items[::-1])["changed"] == []
    with pytest.raises(ValueError, match="duplicate observation"):
        replay.owner_delta(items + items, items)


def test_original_execution_modules_are_hash_pinned():
    observed = {}

    def checked(path, pin):
        observed[path.name] = sha256(path.read_bytes()).hexdigest()
        assert observed[path.name] == pin

    replay.verify_sources(checked)
    assert set(observed) == set(replay.SOURCE_PINS)


def test_saved_reader_and_detector_guard_fails_closed():
    with pytest.raises(RuntimeError, match="cannot open a waveform reader or run a detector"):
        replay.denied(None)
