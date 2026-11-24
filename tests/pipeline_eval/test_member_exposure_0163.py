import pytest

from member_exposure_0163 import schedule, summarize_streams


def recording():
    inventory = {"segments": [], "window_count": 5}
    documents = []
    for number, sizes in enumerate(((2,), (2, 1))):
        name = f"segment-{number:08d}"
        inventory["segments"].append({"scope": name, "path": f"/raw/{name}", "windows": sum(sizes)})
        chunks = [{"chunk_index": index, "first_sequence": sum(sizes[:index]), "window_count": size,
                   "compressed_bytes": size * 7, "compressed_sha256": f"hash-{number}-{index}"}
                  for index, size in enumerate(sizes)]
        documents.append({"session_id": name, "chunks": chunks, "window_count": sum(sizes)})
    return inventory, documents


def test_parity_continues_across_ragged_segments():
    visits, members = schedule(*recording())
    assert visits == [0, 0, 1, 1, 2]
    assert [m["first_visit"] for m in members] == [0, 2, 4]
    assert sum(m["compressed_bytes"] for m in members[::2]) == 21


def test_rejects_decoded_sequence_gap_and_incomplete_segment_roster():
    inventory, docs = recording()
    with pytest.raises(ValueError):
        schedule(inventory, docs[:1])
    docs[1]["chunks"][1]["first_sequence"] += 1
    with pytest.raises(ValueError, match="gap"):
        schedule(inventory, docs)


def probes():
    return [{"receiver_id": radio, "visit_index": visit, "channel": 3, "actual_rf_hz": 100,
             "valid_start_counter": visit * 20 + radio, "candidates": [1] if visit in (1, 3) else []}
            for visit in range(5) for radio in (0, 1)]


def test_exposure_uses_actual_counter_gaps_and_counts_empty_lanes():
    visits, _ = schedule(*recording())
    admitted, streams = summarize_streams(visits, {"sample_rate_hz": 10, "probes": probes()})
    assert admitted == 5
    for stream in streams:
        assert (stream["opportunities"], stream["retained"], stream["nonempty"], stream["retained_nonempty"]) == (5, 3, 2, 1)
        assert (stream["longest_original_gap_s"], stream["longest_retained_gap_s"]) == (2, 6)


@pytest.mark.parametrize("bad", (probes()[:-1], probes() + probes()[-1:]))
def test_requires_exactly_one_row_for_each_receiver(bad):
    visits, _ = schedule(*recording())
    with pytest.raises(ValueError, match="stereo"):
        summarize_streams(visits, {"sample_rate_hz": 10, "probes": bad})
