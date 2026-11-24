from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3.alternate_original_members import member_spans, project, report_adapter
from reports.ALGO08.v3.alternate_original_members_0163 import restricted_binding, restricted_request


def digest(value):
    return "sha256:" + sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def sample_members():
    inventory = dict(window_count=10, segments=[
        dict(path="/original/a", scope="segment-a", windows=2, manifest_digest="a-pin"),
        dict(path="/original/b", scope="segment-b", windows=8, manifest_digest="b-pin"),
    ])
    manifests = []
    for segment, counts in zip(inventory["segments"], ((2,), (3, 5)), strict=True):
        chunks = [dict(chunk_index=i, first_sequence=sum(counts[:i]), window_count=count,
                       compressed_bytes=(i + 1) * 10, uncompressed_bytes=count * 80,
                       index_bytes=count * 3, payload_relative_path=f"iq-{i}.zst") for i, count in enumerate(counts)]
        manifests.append(dict(receiver_ids=[0, 1], window_ms=20, window_count=sum(counts),
                              session_id=segment["path"].split("/")[-1], chunks=chunks))
    return inventory, manifests


def test_global_ordinal_uses_signed_short_members_and_does_not_reset():
    inventory, manifests = sample_members()
    assert [(m["first_visit"], m["stop_visit"], m["retained"]) for m in member_spans(inventory, manifests)] == [
        (0, 2, True), (2, 5, False), (5, 10, True)]
    manifests[1]["chunks"][1]["first_sequence"] = 4
    with pytest.raises(ValueError, match="Unordered"):
        member_spans(inventory, manifests)


def test_projection_keeps_measurements_and_clocks_with_explicit_skips():
    inventory, manifests = sample_members()
    provinces = dict(window_count=10, processed_windows=8, invalid_capture=2,
                     excluded_windows=[dict(visit=0), dict(visit=3)], detector_sha256="sha256:detector")
    probes = [dict(visit_index=i, receiver_id=rx, channel=1, candidates=[{"cfo": i}])
              for i in range(10) if i not in (0, 3) for rx in (0, 1)]
    source = dict(raw_recording_authority_digest="raw", input_manifest_sha256="inventory", probes=probes,
                  analysis_manifest_sha256=digest(["cancellation", "raw", "detector", probes]))
    native = dict(source=source, provenance=provinces, delivery_clocks=[dict(time=i * 9) for i in range(10)])
    restricted, scope = project(native, member_spans(inventory, manifests), digest)
    provenance = restricted["provenance"]
    assert restricted["delivery_clocks"] == native["delivery_clocks"]
    assert restricted["source"]["probes"] == [p for p in probes if p["visit_index"] not in (2, 3, 4)]
    assert provenance["research_sampling"]["skipped_acquisition_windows"] == [2, 3, 4]
    assert provenance["excluded_windows"] == [dict(visit=0)]
    assert scope["retained"]["processed_visits"] == 6
    assert scope["retained"]["compressed_bytes"] == 30
    assert len(native["source"]["probes"]) == 16

    def report(*_):
        return dict(window_count=10, counts=dict(processed=6, invalid_capture=1, skipped_fast_score=0))

    assert report_adapter(report, "recording", "run", restricted)["counts"] == dict(
        processed=6, invalid_capture=1, skipped_fast_score=0, skipped_acquisition=3)


def test_routed_and_independent_publication_requests_resolve_the_same_derived_packet(tmp_path):
    original = dict(native_file="/signed/packet.json", native_sha256="full", admitted=80, session="signed-session",
                    inventory="original-inventory", recording="original-recording", offer_sha256="original-offer")
    parent = dict(request="/signed/request.json", packets={"/signed/request.json": "original-request"}, admitted=80)
    packet, path = tmp_path / "restricted-native.json", tmp_path / "restricted-request.json"
    private = restricted_request(original, packet, "derived", 39)
    path.write_text(json.dumps(private))
    bound = restricted_binding(parent, path, packet, "derived", 39)
    opened = json.loads(path.read_text())
    assert bound["request"] == str(path)
    assert bound["packets"][opened["native_file"]] == opened["native_sha256"] == "derived"
    assert bound["admitted"] == opened["admitted"] == 39
    assert bound["packets"][bound["parent_request"]] == "original-request"
    assert {k: opened[k] for k in ("session", "inventory", "recording", "offer_sha256")} == {
        k: original[k] for k in ("session", "inventory", "recording", "offer_sha256")}
