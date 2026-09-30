from grant_queue_origin import run


def test_internal_grant_record_preserves_session_rf_and_seven_bytes():
    result = run()
    assert result["case_count"] == 366
    assert result["memcpy_calls"] == 366
    assert result["rx_to_tx_composed"] is True
