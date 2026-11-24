import importlib
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return importlib.import_module("decoded_allocation_trial")


def test_original_owned_output_is_forwarded_by_identity_and_reuse_is_observed(trial):
    class Heap:
        def classify(self, raw):
            return "heap", id(raw)

    monitor = trial.Monitor(Heap())
    data = b"X"*trial.PHYSICAL_WINDOW_BYTES
    for _ in range(2):
        assert monitor.read(lambda n: data, trial.PHYSICAL_WINDOW_BYTES) is data
    assert [row["slot"] for row in monitor.reads] == [0, 0]
    with pytest.raises(ValueError, match="independently owned"):
        monitor.read(lambda n: memoryview(data), len(data))


def test_process_policy_changes_only_the_one_glibc_threshold(trial):
    calls = []
    process = trial.Allocator.__new__(trial.Allocator)
    process.mallopt = lambda key, value: calls.append((key, value)) or True
    process.policy("stock")
    assert calls == []
    process.policy("heap")
    assert calls == [(trial.MMAP_THRESHOLD, 2*1024**2)]
    process.mallopt = lambda *_: 0
    with pytest.raises(ValueError, match="not accepted"):
        process.policy("heap")
