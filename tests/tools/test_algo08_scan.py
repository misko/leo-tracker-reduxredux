from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import json

from leo.contracts.digests import canonical_digest
from tools import algo08_scan


def test_empty_observations_withhold_both_arms_without_orbits():
    from tools.algo08_position import solve
    decision, packet, _ = solve({"source": {"probes": []}}, None, None)
    assert decision["status"] == "withheld" and packet is None
    assert decision["arms"] == {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}


def test_verified_windows_keep_their_capture_identity(monkeypatch):
    calls = []
    @contextmanager
    def detector(method, edge, **assets):
        assert method == "cancellation" and edge == "upper"
        def measure(window):
            calls.append(window.acquisition["global_visit"])
            return [dict(receiver_id=rx, channel=1, candidates=[]) for rx in window.receiver_ids]
        yield measure
    def windows():
        for i in (0, 1):
            receipt = dict(host_delivery_clock=dict(realtime_ns=900+i, monotonic_ns=700+i))
            if i == 0:
                receipt["utc_clock_bracket"] = dict(sample_counter=5)
            yield SimpleNamespace(acquisition=dict(retune_receipt=json.dumps(receipt), generation=1,
                global_visit=i, sample_start=5+i*200000, sample_end=5+(i+1)*200000,
                complete=not i, quality_flags=[], validity_authority="provider_attested",
                validity_includes_guard=True, actual_if_center_hz=1), target=dict(edge="upper"),
                samples=SimpleNamespace(shape=(200000,2,2)), sample_rate_hz=10_000_000,
                iq_sha256="sha256:"+str(i)*64)
    segment = SimpleNamespace(receiver_ids=(0,1), reader=SimpleNamespace(
        manifest=SimpleNamespace(sample_rate_hz=10_000_000)), radio={"serial":"r"}, windows=windows)
    monkeypatch.setattr(algo08_scan, "FastSegmentSource", lambda _: segment)
    monkeypatch.setattr(algo08_scan, "detector", detector)
    doc = algo08_scan.acquire("session", "inventory", dict(segments=[{}],window_count=2), Path("."))
    assert calls == [0]
    assert doc["source"]["raw_recording_authority_digest"] == canonical_digest(
        ["inventory", ["sha256:"+"0"*64, "sha256:"+"1"*64]])
    report = algo08_scan.scan_report("recording", "algo08-id", doc)
    assert report["counts"] == dict(processed=1, skipped_fast_score=0, invalid_capture=1)
    assert len(doc["source"]["probes"]) == 2
