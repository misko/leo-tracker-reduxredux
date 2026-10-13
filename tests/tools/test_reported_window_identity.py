from audit_reported_window_identity import summarize


def probe(channel=1, receiver=0, counter=100, payload=20, start=0, passed=True):
    return {
        "receiver_id": receiver,
        "valid_start_counter": counter,
        "payload_start_sample": payload,
        "probe_start_ms": start,
        "channel": channel,
        "candidates": [{"passed_fractional_margin_gate": passed}],
    }


def test_two_rf_labels_on_the_same_reported_window_are_flagged():
    result = summarize([probe(1), probe(5)])
    assert result["distinct_metadata_keys"] == 1
    assert result["repeated_keys"] == 1
    assert result["cross_band_repeated_keys"] == 1
    assert result["low_passing_probes"] == result["high_passing_probes"] == 1


def test_receiver_counter_payload_or_probe_start_distinguishes_source_metadata():
    result = summarize(
        [probe(), probe(receiver=1), probe(counter=101), probe(payload=21), probe(start=1)]
    )
    assert result["distinct_metadata_keys"] == 5
    assert result["repeated_keys"] == 0


def test_multiple_passing_candidates_count_one_probe_and_failed_candidates_stay_exposures():
    passed, failed = probe(), probe(5, counter=200, passed=False)
    passed["candidates"].append({"passed_fractional_margin_gate": True})
    result = summarize([passed, failed])
    assert result["passing_probes_by_channel"]["1"] == 1
    assert result["reported_exposures_by_channel"]["5"] == 1
    assert result["high_passing_probes"] == 0
    assert result["channels_with_pass"] == 1
