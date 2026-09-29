from analyze import ROOT, predict_bounded_drift, predict_last, predict_last_two, summarize


def visit(counter, rate, lo, frequencies):
    return {"counter": counter, "rate": rate, "lo": lo, "frequencies": frequencies}


def test_last_prediction_corrects_changed_lo():
    assert predict_last(visit(0, 1, 100, [5]), visit(10, 1, 110, [])) == [-5]


def test_last_two_extrapolates_in_absolute_frequency():
    older = visit(0, 1, 100, [10])
    previous = visit(10, 1, 105, [15])
    current = visit(20, 1, 110, [])
    assert predict_last_two(older, previous, current) == [20]


def test_bounded_drift_uses_only_nearest_causal_history():
    older = visit(0, 1, 0, [0, 100_000])
    previous = visit(10, 1, 0, [10_000, 160_000])
    current = visit(20, 1, 0, [])
    assert predict_bounded_drift(older, previous, current) == [20_000]


def test_summary_counts_cold_hits_in_full_denominator():
    rows = [
        {**visit(0, 1, 0, [1]), "key": ("s", 1)},
        {**visit(1, 1, 0, [1, 10_000]), "key": ("s", 1)},
    ]
    report = summarize(rows, ROOT / "AGENTS.md", "test")
    bank = report["last_prior_oracle_seed_bank"]
    assert report["cold_start_positive_entries"] == 1
    assert report["standard_positive_entries"] == 3
    assert bank["eligible_positive_entries"] == 2
    assert bank["within_8khz"] == 1
    assert bank["prospective_full_denominator_coverage"] == 1 / 3
