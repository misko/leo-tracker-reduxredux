from tools.ds7_cfo_wave2_run import summarize_held


def test_held_summary_does_not_fit_held_values() -> None:
    rows = [
        {
            "receiver_id": 0,
            "method": "ordinary_profile",
            "training": True,
            "state": "supported",
            "support_center_utc_ns": 0,
            "cfo_hz": 10.0,
        },
        {
            "receiver_id": 0,
            "method": "ordinary_profile",
            "training": True,
            "state": "supported",
            "support_center_utc_ns": 1_000_000_000,
            "cfo_hz": 12.0,
        },
        {
            "receiver_id": 0,
            "method": "ordinary_profile",
            "training": False,
            "state": "supported",
            "support_center_utc_ns": 2_000_000_000,
            "cfo_hz": 15.0,
        },
    ]

    result = summarize_held(rows, 0, "ordinary_profile")

    assert result["held_errors_hz"] == [1.0]
    assert result["held_rms_hz"] == 1.0
