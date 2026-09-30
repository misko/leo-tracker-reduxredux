from bind_ds8_labels import check_binding


def fixture():
    label = dict(
        session_id="session",
        track_id="track",
        receiver_id=0,
        probe=dict(channel=2, edge="upper"),
        start_utc_ns=10000,
        end_utc_ns=20000,
    )
    track = dict(
        dataset="DS8",
        session="session",
        track_id="track",
        receiver=0,
        channel=2,
        edge="upper",
        start_utc_ns=10000,
        end_utc_ns=20000,
    )
    return label, track


def test_rounding_tolerance_does_not_replace_exact_track_binding():
    label, track = fixture()
    label["start_utc_ns"] += 70
    assert all(check_binding(label, track).values())
    label["track_id"] = "different"
    assert not all(check_binding(label, track).values())


def test_binding_rejects_receiver_channel_and_time_mismatch():
    for key, value in [("receiver", 1), ("channel", 3), ("start_utc_ns", 12000)]:
        label, track = fixture()
        track[key] = value
        assert not all(check_binding(label, track).values())
