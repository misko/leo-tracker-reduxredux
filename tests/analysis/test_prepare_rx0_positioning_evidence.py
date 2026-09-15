from tools.prepare_rx0_positioning_evidence import (
    longest_track_per_lane,
    normalized_receiver_ids,
    reference_utc_ns,
    rf_document,
)


def track(channel, edge, span, observations, tracklet_id):
    return {
        "channel": channel,
        "edge": edge,
        "span_s": span,
        "observations": observations,
        "tracklet_id": tracklet_id,
        "time_s": list(range(observations)),
        "cfo_hz": [float(index) for index in range(observations)],
    }


def test_longest_track_selection_is_lane_local_and_deterministic():
    tracks = [
        track(2, "upper", 20, 5, "z"),
        track(1, "lower", 21, 5, "b"),
        track(1, "lower", 21, 6, "a"),
        track(2, "upper", 19, 20, "a"),
    ]
    selected = longest_track_per_lane(tracks)
    assert [(row["channel"], row["edge"], row["tracklet_id"]) for row in selected] == [
        (1, "lower", "a"),
        (2, "upper", "z"),
    ]


def test_receiver_id_normalizes_published_scalar_and_list():
    assert normalized_receiver_ids(0) == [0]
    assert normalized_receiver_ids("0") == [0]
    assert normalized_receiver_ids([0]) == [0]


def test_rf_export_does_not_copy_catalogue_candidates_or_observer():
    chosen = track(1, "lower", 21, 6, "track-a")
    chosen["fields"] = {"0": {"top_training": [{"catalog_number": 123}]}}
    record = {
        "session_id": "scan-hop-test",
        "capture_start_utc": "2026-09-14T15:28:34.123456Z",
        "sample_rate_hz": 10_000_000,
        "receiver_ids": [0],
        "screen": {
            "tracks": [chosen],
            "snapshot_digest": "sha256:" + "a" * 64,
            "snapshot_collected_utc_ns": 1,
            "observer": {"latitude_deg": 37.0},
        },
    }
    document = rf_document(record, "snapshot.tle")
    encoded = str(document)
    assert "catalog_number" not in encoded
    assert "observer" not in encoded
    assert document["inventory"]["known_site_candidate_fields_used"] is False
    assert document["series"][0]["candidate_ids"][-1] == "track-a:5"
    assert reference_utc_ns(record["capture_start_utc"]) == 1_789_399_714_123_456_000
