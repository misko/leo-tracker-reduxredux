import pytest

from tools.plot_scanner_candidate_overlays import comparison_table, top_three_analysis, track_pages


def test_track_pages_are_chronological_complete_and_bounded():
    tracks = [
        {"time_s": [start], "channel": channel, "edge": "upper", "tracklet_id": str(start)}
        for start, channel in [(8, 1), (2, 4), (5, 2), (1, 3), (7, 1), (4, 2), (3, 4)]
    ]
    pages = track_pages(tracks, page_size=3)
    assert [len(page) for page in pages] == [3, 3, 1]
    assert [track["time_s"][0] for page in pages for track in page] == [1, 2, 3, 4, 5, 7, 8]


def test_track_pages_reject_invalid_page_size():
    with pytest.raises(ValueError, match="positive"):
        track_pages([], page_size=0)


def test_top_three_analysis_compares_leader_to_best_heldout_runner():
    candidates = [
        {"name": "A", "catalog_number": 1, "training_rms_hz": 10, "heldout_rms_hz": 20},
        {"name": "B", "catalog_number": 2, "training_rms_hz": 15, "heldout_rms_hz": 100},
        {"name": "C", "catalog_number": 3, "training_rms_hz": 18, "heldout_rms_hz": 50},
        {"name": "D", "catalog_number": 4, "training_rms_hz": 19, "heldout_rms_hz": 21},
    ]
    track = {
        "channel": 1,
        "edge": "upper",
        "time_s": [1, 2],
        "fields": {"0": {"top_training": candidates}},
    }
    result = top_three_analysis(track)
    assert [item["catalog_number"] for item in result["candidates"]] == [1, 2, 3]
    assert result["best_runner"]["catalog_number"] == 3
    assert result["heldout_ratio"] == 2.5
    assert result["heldout_reduction_percent"] == 60
    table = comparison_table([track])
    assert "A / 1: 10.0 / 20.0 Hz" in table
    assert "2.50× / 60.0% lower" in table
