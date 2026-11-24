"""Check archive eligibility and the exact guarded raw adapter call."""

from contextlib import contextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from north_orbit_index_raw import main
from north_orbit_index_trial import HOUR_NS, diagnostics, snapshot_census


def test_census_preserves_current_stamps_and_distinct_content():
    cutoff = 73*HOUR_NS
    entries = [SimpleNamespace(collected_utc_ns=cutoff - age*HOUR_NS, sha256=digest, byte_size=size)
               for age, digest, size in [(0, "a", 100), (48, "a", 100), (72, "b", 120), (73, "c", 90), (-1, "d", 80)]]
    counts = snapshot_census(entries, cutoff)
    assert counts["48"] == dict(references=2, unique_bodies=1, total_bytes=200, unique_bytes=100, body_digests=["a"])
    assert counts["72"] == dict(references=3, unique_bodies=2, total_bytes=320, unique_bytes=220, body_digests=["a", "b"])


def test_adapter_keeps_original_guarded_receiver_args_and_charges_prep(monkeypatch, tmp_path):
    import continued_cfo
    import north_orbit_index_raw

    output = tmp_path/"containing"
    bound = []

    @contextmanager
    def preparation(audit):
        bound.append(True)
        yield
        audit["attempts"] = [{"guard": True}]
        bound.pop()

    def original(library, argv, *, guarded_pack):
        assert bound and library is None and guarded_pack == tmp_path/"guarded"
        assert argv == ["--recording", "/tmp/original", "--region", "/tmp/offer", "--output", str(output)]

    monkeypatch.setattr(north_orbit_index_raw, "bind_runtime", preparation)
    monkeypatch.setattr(continued_cfo, "raw_entry", original)
    main(["--anchored-cfo-pack", str(tmp_path/"guarded"), "--recording", "/tmp/original", "--output", str(output),
          "--region", "/tmp/offer"])
    audit = json.loads((tmp_path/"orbits-indexed.json").read_bytes())
    assert audit["attempts"] == [{"guard": True}]
    assert len(audit["adapter_sha256"]) == 64


def test_verified_diagnostics_compare_proof_and_fallback_rather_than_clocks():
    source = dict(early_regional=[dict(result=dict(probes_evaluated=25, stop="inside_score"), cpu_s=1.)],
                  solve=dict(orbit_policy="stock"), route_details=dict(exterior={"evaluated": True}, decision="complete"))
    verified = diagnostics(source)
    source["early_regional"][0]["cpu_s"] = 2.
    assert diagnostics(source) == verified
    source["route_details"]["fallback_clocks"] = {"cpu_s": 2.}
    assert diagnostics(source) != verified and diagnostics(source)["infer_fallback"]
