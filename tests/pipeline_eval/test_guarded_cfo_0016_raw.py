import fcntl
from hashlib import sha256
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import guarded_cfo_0016_raw as trial
import guarded_cfo_0016_stage as stage


def test_candidate_first_commands_preserve_the_original_input(tmp_path):
    commands = trial.commands(tmp_path, "pack", "named")
    assert tuple(commands) == trial.ORDER == ("candidate", "stock")
    candidate, stock = [list(map(str, commands[mode])) for mode in trial.ORDER]
    for flag, expected in (("--recording", trial.RECORDING), ("--region", trial.PRIOR / "offer.json"),
                           ("--archive", trial.PRIOR / "tle")):
        assert candidate[candidate.index(flag) + 1] == stock[stock.index(flag) + 1] == str(expected)
    assert set(trial.ROUTE_FLAGS) <= set(candidate)
    assert candidate[candidate.index("--anchored-cfo-pack") + 1] == "pack"
    assert "--select-before-cfo" not in candidate


def test_receipt_requires_all_payload_and_index_pages():
    payload = {"cached_pages": 242128, "observed_file_pages": 242128}
    index = {"cached_pages": 543, "observed_file_pages": 543}
    assert stage.fully_resident({"payload": payload, "index": index})
    assert not stage.fully_resident({"payload": payload, "index": index | {"cached_pages": 542}})
    assert not stage.fully_resident({"payload": payload | {"cached_pages": 0}, "index": index})


def test_relative_device_read_latency_requires_enough_reads():
    assert stage.average_read_ms((15, 100), (23, 300)) == 25
    assert stage.average_read_ms((15, 100), (22, 300)) is None
    with pytest.raises(ValueError, match="regressed"):
        stage.average_read_ms((15, 100), (14, 300))


def test_bounded_signed_copy_releases_lock_before_every_yield(tmp_path, monkeypatch):
    source, output, lock_file = [tmp_path / name for name in ("input", "output", "lock")]
    contents = b"12345678"
    source.write_bytes(contents)
    lock_file.touch()
    blocks, waits = [], []
    monkeypatch.setattr(stage, "BLOCK", 3)

    def sleep_unlocked(seconds):
        with lock_file.open("rb") as independent:
            fcntl.flock(independent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        waits.append(seconds)

    monkeypatch.setattr(stage, "sleep", sleep_unlocked)
    digest = sha256(contents).hexdigest()
    stats = SimpleNamespace(wait_s=0.0, progress=lambda _, count: blocks.append(count))
    with lock_file.open("rb") as lock:
        stage.copy_member(source, output, len(contents), digest, lock, stats)
        assert os.fstat(lock.fileno()).st_size == 0
        with pytest.raises(ValueError, match="bounded regular file"):
            stage.copy_member(source, tmp_path / "bad-size", len(contents)-1, digest, lock, stats)
    assert output.read_bytes() == contents
    assert blocks == [3, 3, 2] and len(waits) == len(blocks) and min(waits) >= .025
