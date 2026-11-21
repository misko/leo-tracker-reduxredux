from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import json

from leo.contracts.digests import canonical_digest
from tools import algo08_scan


def test_empty_observations_withhold_both_arms_without_orbits():
    from tools.algo08_position import solve
    from leo.contracts.algo08_region import Algo08Region
    decision, packet, _ = solve({"source": {"probes": []}}, None, None, Algo08Region((1, 2), 25))
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


def test_offers_and_annotated_publications_share_only_the_detector(tmp_path, monkeypatch):
    from leo.contracts.algo08_region import Algo08Region
    from leo.storage.fast_scan import FastScanStore
    inv = dict(window_count=1)
    sha = canonical_digest(inv)
    session = "fast-" + sha[7:39]
    monkeypatch.setattr(FastScanStore, "inventory", lambda *a, **k: (session, sha, inv))
    monkeypatch.setattr(algo08_scan, "PINS", {"cancellation-factors.so": "dummy"})
    (tmp_path / "cancellation-factors.so").write_bytes(b"binary")
    monkeypatch.setattr(algo08_scan, "sha256_digest", lambda _: "sha256:dummy")
    called = []
    def acquire(*args):
        called.append(1)
        return dict(source=dict(session_id=session, input_manifest_sha256=sha,
                    raw_recording_authority_digest="raw", probes=[],
                    analysis_manifest_sha256=canonical_digest(["cancellation", "raw", "dummy", []])),
                    provenance=dict(rf_mapping_authorities=[], window_count=1, processed_windows=0,
                                    invalid_capture=1))
    monkeypatch.setattr(algo08_scan, "acquire", acquire)
    def run(center, width=25, screen=None, ref=None):
        return algo08_scan.analyze(tmp_path / "sealed", tmp_path, tmp_path, tmp_path,
                                   Algo08Region(center, width, screen), ref)
    first = run((10, 25))
    assert run((10., 25.), screen=(10, 25)) == first
    other_reference = run((10, 25), ref=dict(latitude_deg=11., longitude_deg=26.))
    assert other_reference["terminal_sha256"] == first["terminal_sha256"]
    receipts = [first, other_reference, run((11, 25)), run((10, 25), width=26),
                run((10, 25), screen=(10, 24))]
    assert len({r["run_id"] for r in receipts}) == 5
    assert called == [1] and all(r["decision"] == "withheld" for r in receipts)


def test_cli_offer_override_drops_station_reference(tmp_path, monkeypatch):
    station = tmp_path / "station.json"
    station.write_text('{"center":[10,20],"width_km":25}')
    alternate = tmp_path / "alternate.json"
    alternate.write_text('{"center":[-20,-35],"width_km":40}')
    monkeypatch.setenv("ALGO08_REGION_FILE", str(station))
    monkeypatch.setenv("ALGO08_EVALUATION_LATITUDE", "10.01")
    monkeypatch.setenv("ALGO08_EVALUATION_LONGITUDE", "20.01")
    calls = []
    monkeypatch.setattr(algo08_scan, "analyze", lambda *args, **kw: calls.append(args[4:6]))
    args = [flag for option in ("--recording", "--bulk-root", "--assets", "--archive")
            for flag in (option, str(tmp_path))]
    algo08_scan.main(args)
    algo08_scan.main(args + ["--region", str(alternate)])
    algo08_scan.main(args + ["--region", str(alternate), "--evaluation-reference", "-20.01", "-35.01"])
    assert [(r.center, ref) for r, ref in calls] == [
        ((10., 20.), dict(latitude_deg=10.01, longitude_deg=20.01)),
        ((-20., -35.), None), ((-20., -35.), dict(latitude_deg=-20.01, longitude_deg=-35.01))]
