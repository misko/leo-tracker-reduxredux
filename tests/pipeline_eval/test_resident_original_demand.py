from types import SimpleNamespace

import pytest

from leo.storage.fast_scan import FastSegmentSource
from reports.ALGO08.v3 import legacy_first_map_input as producer
from reports.ALGO08.v3.resident_original_demand import demand_eligible
from tools.pipeline_eval.variants.experimental import receiver_member_prefetch as prefetch


@pytest.mark.parametrize("bounded, submits", [(False, 1), (True, 0)])
def test_only_normal_source_dispatches_base_class_prefetch(tmp_path, monkeypatch, bounded, submits):
    stock = FastSegmentSource

    class Prefix(stock):
        pass

    source = Prefix if bounded else stock
    visits = [SimpleNamespace(sequence=i) for i in range(2)]
    chunks = [SimpleNamespace(first_sequence=i, window_count=1, payload_relative_path=f"{i}.zst",
                              compressed_bytes=100) for i in range(2)]
    scanner = SimpleNamespace(FastSegmentSource=source, acquire=lambda *args: None)
    boot = SimpleNamespace(staged_scanner=lambda sources, detector=None: scanner)
    item = object.__new__(source)
    item.reader = SimpleNamespace(path=tmp_path, manifest=SimpleNamespace(chunks=chunks))
    item.start_sequence, item.stop_sequence = 0, 2
    monkeypatch.setattr(stock, "windows", lambda *_: (visit for visit in visits))
    monkeypatch.setattr(prefetch, "prefetch_member", lambda *_: None)
    with producer.binding(boot, None, None, None, None, {}, {}, build_maps=False):
        boot.staged_scanner({}, detector=object())
        fused_windows = source.__dict__["windows"]
        with prefetch.compressed_member_prefetch() as stats:
            assert (source.__dict__["windows"] is fused_windows) == bounded
            assert list(item.windows()) == visits
        assert stats.submitted == submits


def test_synchronous_route_requires_unchanged_complete_resident_mount(tmp_path, monkeypatch):
    import visit_frame_raw_0016

    paths = [tmp_path / "first", tmp_path / "second"]
    monkeypatch.setattr(visit_frame_raw_0016, "resident", lambda paths: {"members": len(paths)})
    assert demand_eligible(paths, lambda: paths)
    assert not demand_eligible(paths, lambda: paths[:-1])
    monkeypatch.setattr(visit_frame_raw_0016, "resident", lambda paths: {"members": 1})
    assert not demand_eligible(paths, lambda: paths)

    def mutable():
        raise ValueError("not the read-only original mount")

    assert not demand_eligible(paths, mutable)
