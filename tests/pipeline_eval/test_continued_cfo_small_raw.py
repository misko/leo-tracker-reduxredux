from hashlib import sha256
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import continued_cfo_small_raw as trial


def roster():
    return [(trial.CASE.windows, trial.CASE.id, trial.CASE.binding_sha),
            (29, "DS30-0108", "d"), (18, "DS30-0227", "e"),
            (92, "DS30-0180", "f"), (124, "DS30-0102", "g"),
            *((200 + n, f"extra-{n}", "h") for n in range(450))]


def test_selection_only_uses_lengths_and_label():
    picked = trial.enroll(list(reversed(roster())))
    assert picked["eligible"] == [(29, "DS30-0107", trial.CASE.binding_sha)]
    assert picked["excluded"] == ["DS30-0102", "DS30-0180", "DS30-0227"]
    changed = roster()
    changed[-1] = (32, "extra", "h")
    with pytest.raises(ValueError, match="exception"):
        trial.enroll(changed)


def test_complete_extent_and_aggregate_cap():
    trial.capacity(33_519_983, 78_609, 3_542)
    with pytest.raises(ValueError, match="extent"):
        trial.capacity(33_519_984, 78_609, 3_542)


def test_copy_hash_size_and_exclusivity(tmp_path):
    source = tmp_path / "source"
    contents = b"sealed"
    source.write_bytes(contents)
    digest = sha256(contents).hexdigest()
    target = tmp_path / "target"
    assert trial.copy_verified(source, target, len(contents), digest) == len(contents)
    assert target.read_bytes() == contents
    with pytest.raises(FileExistsError):
        trial.copy_verified(source, target, len(contents), digest)
    with pytest.raises(ValueError, match="size"):
        trial.copy_verified(source, tmp_path / "bad-size", len(contents) - 1, digest)
    with pytest.raises(ValueError, match="digest"):
        trial.copy_verified(source, tmp_path / "bad-digest", len(contents), "0" * 64)


def test_pair_keeps_the_original_path_and_publication_guards(tmp_path):
    stock, candidate = [list(map(str, trial.command(mode, tmp_path, "named", "python")))
                        for mode in trial.CASE.order]
    for flag in ("--recording", "--archive", "--region"):
        assert stock[stock.index(flag) + 1] == candidate[candidate.index(flag) + 1]
    assert set(trial.ROUTE_FLAGS) <= set(candidate)
    assert "--named-survivor-finish" in candidate
    assert "--withhold-empty-family-calibration" in candidate
