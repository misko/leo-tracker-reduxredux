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
