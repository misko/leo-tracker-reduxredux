import gzip
from hashlib import sha256
import json

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
    data = (replay.HERE / "measurements/prospective-0316-solver.json.gz").read_bytes()
    assert sha256(data).hexdigest() == "a253e1733851a84cf6cd08b619e99e82f64de5addf57dd43734ea26bf2f4963b"
    sealed = json.loads(gzip.decompress(data))
    observed = {}

    def checked(path, pin):
        assert path.parent == replay.HERE
        observed[path.name] = pin

    replay.verify_sources(checked)
    assert observed == sealed["sources"]
    assert replay.BASE == sealed["research_base"]


def test_execution_rejects_modified_module(monkeypatch, tmp_path):
    from reports.ALGO08.v3.empty_bootstrap import checked

    monkeypatch.setattr(replay, "HERE", tmp_path)
    (tmp_path / "unified_short_bootstrap.py").write_text("# changed execution\n")
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        replay.verify_sources(checked)


def test_saved_reader_and_detector_guard_fails_closed():
    with pytest.raises(RuntimeError, match="cannot open a waveform reader or run a detector"):
        replay.denied(None)
