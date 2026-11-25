"""Check the fixed enrollment, physical pause gate and ordinary-grid mode."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import combined_second_original as candidate
    import combined_second_stage as stage
    import combined_small_panel_entry as entry

    return candidate, stage, entry


def test_middle_selection_uses_visits_and_label(modules):
    candidate, _, _ = modules
    rows = [
        dict(case="DS30-0018", window_count=1790),
        dict(case="DS30-0050", window_count=1810),
        dict(case="DS30-0004", window_count=90),
        dict(case="DS30-0003", window_count=6700),
    ]
    assert [r["case"] for r in candidate.select_rows(rows)] == ["DS30-0018", "DS30-0050"]


def test_stage_refuses_official_child_and_busy_source(modules, monkeypatch):
    from guarded_stage_idle import Load

    _, stage, _ = modules
    official, queues = [False], {stage.SOURCE: 0, stage.RAID: 0}
    monkeypatch.setattr(stage, "official_active", lambda _: official[0])
    monkeypatch.setattr(stage, "sample", lambda device, now: Load(now(), 0.0, 0, queues[device], 3))
    assert stage.guarded_sample(1, lambda: 0.0).in_flight == 0
    official[0] = True
    assert stage.guarded_sample(1, lambda: 0.0).in_flight > 2
    official[0] = False
    queues[stage.RAID] = 1
    assert stage.guarded_sample(1, lambda: 0.0).in_flight > 2


def test_cache_only_stops_on_miss(modules, monkeypatch):
    _, stage, _ = modules

    def miss(*args):
        raise BlockingIOError("no cached pages")

    monkeypatch.setattr(stage.os, "preadv", miss)
    stream = SimpleNamespace(fileno=lambda: 1, tell=lambda: 0)
    with pytest.raises(BlockingIOError):
        stage.read_nowait(stream, 32)


def test_copy_gap_expires_before_official_retry(modules, tmp_path):
    _, stage, _ = modules
    (tmp_path / "rows.jsonl").touch()
    instant = [50_000_000_000]
    gap = stage.LiveGap(
        tmp_path, clock=lambda: instant[0], observe=lambda *_: {"unix_ns": 49_000_000_000}
    )
    assert gap.available()
    instant[0] = 63_000_000_000
    assert not gap.available()


def test_ordinary_exporter_is_not_replaced(modules, monkeypatch):
    _, _, entry = modules

    def ordinary():
        pass

    handoff = SimpleNamespace(grid_handoff=ordinary, Capture=SimpleNamespace(run=ordinary))
    monkeypatch.setattr(
        entry,
        "load_ports",
        lambda boot, ordinary_grid: SimpleNamespace(
            grid=SimpleNamespace(handoff=handoff),
            canonical=lambda doc: "raw",
            app=None,
            tracks=None,
            stock=[],
            feature=None,
            config=None,
            bind=lambda *args, **kwargs: nullcontext(),
        ),
    )
    audit = dict(publication_calls=0, cfo={})

    def publish(*_args):
        assert handoff.grid_handoff is ordinary and handoff.Capture.run is ordinary
        return "completed"

    boot = SimpleNamespace(now=lambda: 0.0, clock=lambda _: {})
    wrap = entry.publication(boot, publish, audit, ordinary_grid=True)
    spec = dict(posterior_grid_handoff=dict(sha256=entry.STOCK_GRID_BINARY))
    assert wrap(None, None, spec, SimpleNamespace(native={})) == "completed"
    assert audit["ordinary_grid"]["binary_sha256"] == entry.STOCK_GRID_BINARY
    assert audit["grid"] == {}


def test_future_cache_gate_refuses_one_missing_or_redirection(modules):
    from combined_cache_0208_gate import missing_pages

    roster = [dict(path="/a", size=8192), dict(path="/b", size=4096)]
    observed = [dict(file="/a", size=8192, res=8192), dict(file="/b", size=4096, res=0)]
    assert missing_pages(roster, observed) == [observed[1]]
    observed[1]["file"] = "/redirected"
    with pytest.raises(ValueError, match="signed source roster"):
        missing_pages(roster, observed)


def test_future_cache_read_refuses_any_source_blocks(modules, monkeypatch):
    import combined_cache_0208 as cached

    counters = iter([0, 1])
    monkeypatch.setattr(cached, "read_counters", lambda: next(counters))
    monkeypatch.setattr(cached, "read_nowait", lambda *_: b"cached")
    ledger, interval = cached.SourceReads(), {}
    with pytest.raises(OSError, match="zero-input read"):
        cached.zero_io_read(None, 6, ledger, interval)
    assert interval == dict(returned_bytes=6, input_blocks=1, read_bytes_charged=512)
    assert ledger.source_reads_attempted == ledger.source_reads_metered == 1
    assert ledger.summary("refused", 6)["zero_input_blocks_per_admitted_source_read"] is False


def test_future_cache_eagain_accounts_speculative_io_without_returned_bytes(modules, monkeypatch):
    import errno
    import combined_cache_0208 as cached

    counters = iter([11, 267])
    monkeypatch.setattr(cached, "read_counters", lambda: next(counters))
    monkeypatch.setattr(cached, "range_pages", lambda *_: 1)

    def cold(*_):
        raise BlockingIOError(errno.EAGAIN, "cache miss")

    monkeypatch.setattr(cached, "read_nowait", cold)
    ledger = cached.SourceReads()
    item = dict(target="known/iq", kind="payload")
    with pytest.raises(BlockingIOError, match="cache miss"):
        ledger.read(item, SimpleNamespace(tell=lambda: 0), 4096)
    assert ledger.source_reads_attempted == ledger.source_reads_metered == 1
    assert ledger.source_bytes_returned == 0
    assert ledger.source_read_input_blocks == 256 and ledger.source_read_bytes_charged == 131072
    assert ledger.refused_interval["nowait_errno"] == errno.EAGAIN
    assert ledger.refused_interval["target"] == item["target"]
    assert ledger.summary("refused", 4096)["zero_input_blocks_per_admitted_source_read"] is False


def test_future_cache_census_coverage_and_all_bytes_gate(modules, monkeypatch):
    import errno
    import combined_cache_0208 as cached

    monkeypatch.setattr(cached, "range_pages", lambda *_: 0)
    monkeypatch.setattr(cached, "read_counters", lambda: pytest.fail("Missing page admitted a read"))
    stream = SimpleNamespace(tell=lambda: 0, fileno=lambda: 7)
    ledger = cached.SourceReads()
    with pytest.raises(OSError, match="missing pages"):
        ledger.read(dict(target="known/iq", kind="payload"), stream, 4096)
    assert ledger.range_checks == 1 and ledger.source_reads_attempted == 0

    def forbidden(*_):
        raise PermissionError(errno.EPERM, "read-only census")

    monkeypatch.setattr(cached, "range_pages", forbidden)
    monkeypatch.setattr(cached.os, "fstat", lambda _: SimpleNamespace(st_uid=0))
    ledger = cached.SourceReads()
    with pytest.raises(PermissionError, match="read-only census"):
        ledger.read(dict(target="known/index", kind="index"), stream, 4096)
    assert ledger.source_reads_attempted == 0

    ledger = cached.SourceReads()
    monkeypatch.setattr(cached, "read_counters", lambda: 0)
    monkeypatch.setattr(cached, "read_nowait", lambda *_: b"cached")
    assert ledger.read(dict(target="known/tle", kind="causal"), stream, 6) == b"cached"
    assert ledger.privileged_census_only_ranges == 1 and ledger.privileged_census_only_bytes == 6
    assert ledger.summary("complete", 6)["zero_input_blocks_per_admitted_source_read"] is True
    assert ledger.summary("complete", 7)["zero_input_blocks_per_admitted_source_read"] is False
