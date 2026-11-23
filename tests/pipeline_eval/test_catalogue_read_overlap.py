from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

from reports.ALGO08.v3.catalogue_read_overlap import DemandTrace


class Parser:
    def __init__(self):
        self.catalogues = {}

    def __call__(self, body):
        self.catalogues[body] = body


class Archive:
    def __init__(self):
        self.reads = []

    def list_snapshots(self, provider):
        assert provider == "space-track"
        return [
            SimpleNamespace(path=Path(f"{i}.tle"), collected_utc_ns=i, sha256=str(i), byte_size=1)
            for i in (1, 2, 4)
        ]

    def read(self, source):
        self.reads.append(source.sha256)
        return source.sha256


class Outstanding:
    def done(self):
        return False

    def result(self):
        return b"iq", (1, 2)


def test_ready_member_does_not_start_catalogue_work():
    archive = Archive()
    trace = DemandTrace(archive, Parser, "overlap", 0)
    trace.cutoff = 3
    ready = Future()
    ready.set_result(b"iq")
    assert trace.demand(ready, "member") == b"iq"
    assert not archive.reads
    assert trace.demands[0]["ready_at_demand"]


def test_active_wait_only_primes_past_source_and_failure_restores_empty_parser():
    archive = Archive()
    trace = DemandTrace(archive, Parser, "fallback", 0)
    trace.cutoff = 3
    outstanding = Outstanding()
    assert trace.demand(outstanding, "member") == (b"iq", (1, 2))
    assert not archive.reads
    trace.active_hold = "member"
    trace.demand(outstanding, "member")
    assert tuple(trace.parser.catalogues) == ("1",)
    trace.demand(outstanding, "member")
    assert archive.reads == ["1", "2"]
    assert not trace.primed and not trace.parser.catalogues
    assert trace.primes[-1]["error"] == "ValueError: injected speculative parser failure"
    assert trace.disabled
