import pytest

from reports.ALGO08.v3.catalogue_receipt_residency import (
    INDEX_BODY,
    INDEX_HEADER,
    INDEX_MAGIC,
    INDEX_RECORD_BYTES,
    document_digest,
    index_bodies,
    local_bytes,
    read_coverage,
)


def tiny_index():
    return (INDEX_MAGIC + INDEX_HEADER.pack(2, 1) + b"{}" + INDEX_BODY.pack(b"\xa1" * 32, 1)
            + bytes(INDEX_RECORD_BYTES))


def test_portable_digest_roster_fails_closed_on_extent():
    assert index_bodies(tiny_index()) == {"a1" * 32: 1}
    for body in (tiny_index()[:-1], tiny_index() + b"extra"):
        with pytest.raises(ValueError):
            index_bodies(body)


def test_accessed_metadata_never_replaces_unread_authority():
    digest, absent = "a1" * 32, "b2" * 32
    observed = {f"100-{digest}.tle": 12_000, f"150-{digest}.tle": 4_000}
    offered = {name: digest for name in observed} | {f"125-{absent}.tle": absent}
    found = read_coverage(observed, document_digest(offered), 200, index_bodies(tiny_index()))
    assert (found["opened_references"], found["opened_unique_bodies"], found["verified_bytes"]) == (2, 1, 16_000)
    assert found["index_digest_overlap"] == 1
    assert not found["observed_roster_is_complete"]
    assert not found["catalogue_bytes_available_from_index"]


def test_future_and_unverified_references_fail_closed():
    reference = f"200-{'a1' * 32}.tle"
    with pytest.raises(ValueError):
        read_coverage({reference: 10}, "ignored", 200, {})
    with pytest.raises(ValueError):
        read_coverage({reference: 0}, "ignored", 201, {})


def test_local_receipt_adapter_denies_tle_and_indirect_paths(tmp_path):
    body = tmp_path / "cause.tle"
    body.write_bytes(b"fixture only")
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b"{}")
    alias = tmp_path / "alias.json"
    alias.symlink_to(receipt)
    assert local_bytes(tmp_path, receipt) == b"{}"
    for path in (body, alias):
        with pytest.raises(ValueError):
            local_bytes(tmp_path, path)
