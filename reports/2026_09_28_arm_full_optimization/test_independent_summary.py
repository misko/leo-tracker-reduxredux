from independent_summary import maximum_matches, summarize


def candidate(epoch, cfo, margin):
    return {
        "epoch_sample": epoch,
        "epoch": epoch,
        "acquired_cfo_hz": cfo,
        "tracking_cfo_hz": cfo,
        "exact_score": margin + 0.1,
        "control_score": 0.1,
        "margin": margin,
    }


def test_maximum_matching_does_not_give_duplicate_credit():
    reference = [candidate(10, 100, 0.1), candidate(11, 101, 0.1)]
    native = [candidate(10, 100, 0.1)]
    assert maximum_matches(reference, native) == 1


def test_missing_native_keeps_sealed_denominator():
    context = {"ordinal": 0, "session_id": "s", "visit_index": 1, "rate_hz": 2_500_000}
    windows = {}
    for receiver in range(2):
        for probe in range(11):
            candidates = [
                candidate(rank, rank * 100, 0.1 if rank == 0 else 0.0) for rank in range(8)
            ]
            windows[(receiver, probe)] = {"candidates": candidates}
    result = summarize([context], {("s", 1): windows}, {})
    assert result["totals"]["windows"] == 22
    assert result["totals"]["candidates"] == 176
    assert result["totals"]["reference_positive_hits"] == 22
    assert result["totals"]["recovered_positive_hits"] == 0
    assert result["totals"]["missing_native_windows"] == 22
    assert result["totals"]["ordered_mismatched_candidates"] == 176
