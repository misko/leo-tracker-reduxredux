from reports.ALGO08.v3 import short_prefetch_residency as prefetch


def observation(cached, expected=8):
    return {"observed_members": 1, "unavailable": {}, "observed_file_pages": expected, "cached_pages": cached}


def chunk(visit, *, cached=8, index_cached=8, count=64):
    return {"first_sequence": visit, "window_count": count, "payload": observation(cached),
            "index": observation(index_cached)}


def test_three_neighbors_need_complete_payload_and_index():
    assert prefetch.eligible_triples([chunk(0), chunk(64), chunk(128), chunk(192, cached=7)]) == [0]
    assert prefetch.eligible_triples([chunk(0), chunk(64, index_cached=7), chunk(128)]) == []


def test_partial_chunk_or_nonconsecutive_counts_cannot_qualify():
    assert prefetch.eligible_triples([chunk(0), chunk(64), chunk(192)]) == []
    assert prefetch.eligible_triples([chunk(0), chunk(64), chunk(128, count=21)]) == []
