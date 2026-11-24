import json
from time import time_ns
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import prefetch_prefix_0049 as trial


def test_released_class_retains_its_windows_port_for_prefetch():
    from original_prefix_scaling import bound_source

    from tools.pipeline_eval.variants.experimental.receiver_member_lookahead import (
        following_members,
    )

    chunks = [SimpleNamespace(first_sequence=i * 64, window_count=64) for i in range(8)]

    class Source:
        def __init__(self, entry, *, stop_sequence=None):
            self.reader = SimpleNamespace(manifest=SimpleNamespace(chunks=chunks))
            self.start_sequence, self.stop_sequence = 0, stop_sequence

        def windows(self):
            return iter(())

    original = Source.windows
    with bound_source(Source, {"scope": 0}, 384):
        scoped = Source({"scope": 0})
        assert Source.windows is original
        assert scoped.stop_sequence == 384
        assert list(following_members(scoped).values()) == chunks[1:6]
        with pytest.raises(ValueError, match="Unexpected signed acquisition"):
            Source({"scope": 1})


def test_original_prefix_guard_denies_seventh_member_and_backing_paths(tmp_path):
    from original_prefix_scaling import guard

    enclosed = tmp_path / "iq-000005.ci16.zst"
    audit = guard([enclosed])
    audit("open", (str(enclosed),))
    audit("open", (enclosed.name,))
    with pytest.raises(PermissionError, match="following payload"):
        audit("open", (str(tmp_path / "iq-000006.ci16.zst"),))
    with pytest.raises(PermissionError, match="backing input"):
        audit("open", ("/srv/bulk/original/manifest.json",))


def test_admission_requires_a_fresh_official_deferral(tmp_path, monkeypatch):
    active = tmp_path / "next-official"
    events = active / "events"
    events.mkdir(parents=True)
    monkeypatch.setattr(trial, "OFFICIAL", tmp_path / "archived-control")
    event = events / "001.json"
    event.write_text(json.dumps({"state": "metadata_admitted"}))
    assert not trial.occupied()[1]
    (events / "002.json").write_text(json.dumps({"state": "deferred_storage_busy"}))
    assert trial.occupied()[1]
    monkeypatch.setattr(trial, "time_ns", lambda: time_ns() + 6_001_000_000)
    assert not trial.occupied()[1]
