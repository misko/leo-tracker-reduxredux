import copy

import pytest

from reports.ALGO08.v3.integrated_south import ENTRY, invocation
from reports.ALGO08.v3.integrated_south_score import numerical, original_members


def test_offer_switch_keeps_integrated_flags_and_libraries(tmp_path):
    old = ["timeout", "--kill-after=2s", "75s", "python", "-IB", str(ENTRY),
           "--sparse8-primary", "--verify-original-once", "--history-risk-route", "--cairo-six-sheets",
           "--recording", "old", "--archive", "archive", "--archive-sha256", "old-archive",
           "--region", "old-region", "--output", "old-output", "--short-binary", "pinned.so"]
    request = {"recording": "original", "archive": {"root": "staged", "snapshots_sha256": "archive-pin"},
               "offers": {"containing": "inside", "near-omitted": "outside"}}
    before, after = (invocation(old, request, mode, tmp_path) for mode in request["offers"])
    assert [(i, j) for i, j in zip(before, after, strict=True) if i != j] == [("inside", "outside")]
    assert before[-2:] == ["--short-binary", "pinned.so"]
    assert old[old.index("--recording") + 1] == "old"
    with pytest.raises(ValueError, match="verified-once invocation"):
        invocation([*old, "--legacy-first-map-plan", "old-map"], request, "containing", tmp_path)


def test_signed_scope_checks_every_member_and_index():
    request = dict(session="session", inventory="inventory", issued=2, authority="raw", manifest_sha256="signed")
    chunk = dict(chunk_index=0, compressed_sha256="encoded", index_sha256="index", uncompressed_sha256="decoded",
                 first_sequence=0, window_count=2, compressed_bytes=9, uncompressed_bytes=32)
    member = dict(manifest_sha256="sha256:signed", member_sha256="encoded", index_sha256="index",
                  raw_sha256="decoded", chunk_index=0, first_sequence=0, windows=2, encoded=9, decoded=32,
                  complete_encoded_auth={"cpu_ns": 1}, hash_prefix=False)
    audit = dict(authority_mode="verified-once", finished_raw_authority="raw", members=[member],
                 verified_source=dict(session="session", inventory="inventory", windows=2, raw_authority="raw"))
    assert original_members(audit, request, [chunk])
    assert not original_members(audit, request, [chunk | {"index_sha256": "other"}])
    assert not original_members(audit, request, [chunk, chunk])


def test_numerical_readback_excludes_only_rebound_custody_and_clock():
    old = dict(binding=dict(input_sha256="old", terminal_sha256="old", position_png_sha256="old",
                            model_version="same", owner_sha256="owner"), elapsed_seconds=11, points=[1])
    new = copy.deepcopy(old)
    new["binding"].update(input_sha256="new", terminal_sha256="new", position_png_sha256="new")
    new["elapsed_seconds"] = 9
    assert numerical(old) == numerical(new)
    new["binding"]["owner_sha256"] = "different owner"
    assert numerical(old) != numerical(new)
