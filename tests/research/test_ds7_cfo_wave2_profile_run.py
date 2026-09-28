from tools.ds7_cfo_wave2_profile_run import _line_prediction


def test_profile_prediction_uses_training_rows_only() -> None:
    rows = [
        {
            "receiver_id": 0,
            "method": "robust_profile",
            "training": True,
            "state": "supported",
            "support_center_utc_ns": 0,
            "cfo_hz": 10.0,
            "channel": 3,
            "actual_rf_hz": 11_440_000_000.0,
        },
        {
            "receiver_id": 0,
            "method": "robust_profile",
            "training": True,
            "state": "supported",
            "support_center_utc_ns": 1_000_000_000,
            "cfo_hz": 12.0,
            "channel": 3,
            "actual_rf_hz": 11_440_000_000.0,
        },
        {
            "receiver_id": 0,
            "method": "robust_profile",
            "training": False,
            "state": "supported",
            "support_center_utc_ns": 2_000_000_000,
            "cfo_hz": -1_000_000.0,
            "channel": 3,
            "actual_rf_hz": 11_440_000_000.0,
        },
    ]

    held = {
        "support_center_utc_ns": 2_000_000_000,
        "channel": 3,
        "actual_rf_hz": 11_440_000_000.0,
    }
    assert _line_prediction(rows, 0, "robust_profile", held) == 14.0


def test_profile_prediction_rejects_cross_channel_transfer() -> None:
    rows = [
        {
            "receiver_id": 0,
            "method": "ordinary_profile",
            "training": True,
            "state": "supported",
            "support_center_utc_ns": index * 1_000_000_000,
            "cfo_hz": 10.0 + index,
            "channel": 3,
            "actual_rf_hz": 11_440_000_000.0,
        }
        for index in (0, 1)
    ]
    held = {
        "support_center_utc_ns": 2_000_000_000,
        "channel": 2,
        "actual_rf_hz": 11_190_000_000.0,
    }

    try:
        _line_prediction(rows, 0, "ordinary_profile", held)
    except ValueError as error:
        assert "identical channel" in str(error)
    else:
        raise AssertionError("cross-channel transfer must fail closed")
