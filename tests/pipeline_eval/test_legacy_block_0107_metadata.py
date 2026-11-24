import pytest

from reports.ALGO08.v3.legacy_block_0107_metadata import index_counts


def test_signed_partition_preserves_partial_and_empty_visit():
    sizes = (200000, 136857, 0)
    base = 0
    rows = []
    for number, size in enumerate(sizes):
        rows.append(dict(sequence=number, sample_count=size, payload_offset_bytes=base,
                         payload_bytes=8*size, receiver_count=2, iq_sha256=str(number)))
        base += 8*size
    header = dict(first_sequence=0, window_count=len(rows), uncompressed_bytes=base)
    observed = index_counts(rows, header)
    assert observed["sample_extents"] == {0: 1, 136857: 1, 200000: 1}
    assert [item["sequence"] for item in observed["nonfull"]] == [1, 2]
    rows[2]["payload_offset_bytes"] -= 1
    with pytest.raises(ValueError, match="partition"):
        index_counts(rows, header)


def test_two_recording_gate_requires_both_median_and_summed(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    from legacy_block_0107_score import speedup_gate

    measured = speedup_gate({"fix": 10, "tiny": 1}, {"fix": 7, "tiny": .5})
    assert measured["gates"]["1.6x"] == dict(median=True, sum=False, both=False)
    assert measured["gates"]["2x"] == dict(median=False, sum=False, both=False)
