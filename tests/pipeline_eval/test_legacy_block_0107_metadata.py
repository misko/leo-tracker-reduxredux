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


def test_full_map_argument_projection_preserves_runtime_and_decoder_pin(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    from legacy_block_all_0107 import WORK, move_arguments

    entry = WORK/"reports/ALGO08/v3/legacy_block_all_entry.py"
    scope = ("--recording", "--archive", "--region", "--archive-sha256")
    earlier = [value for name in scope for value in (name, "tiny"+name)]
    initial = ["timeout", "--kill", "75", "python", "-IB", str(entry), "--cairo-residual-layout",
               "--history-risk-route", "--portable-orbit-index", "fixed-index", "--legacy-map-library-sha256", "keep"]
    initial.extend(value for name in (*scope, "--output", "--legacy-map-custody", "--legacy-map-custody-sha256", "--legacy-map-library")
                   for value in (name, "earlier"+name))
    projected = move_arguments(initial, earlier, tmp_path, "sha256:new-tag")
    assert projected[5] == str(entry)
    assert projected[projected.index("--recording")+1] == "tiny--recording"
    assert projected[projected.index("--portable-orbit-index")+1] == "fixed-index"
    assert projected[projected.index("--legacy-map-library-sha256")+1] == "keep"
    assert projected[projected.index("--legacy-map-custody-sha256")+1] == "sha256:new-tag"
