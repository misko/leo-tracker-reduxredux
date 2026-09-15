import pytest

from tools.plot_scanner_candidate_overlays import track_pages


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
