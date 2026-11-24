import pytest

from reports.ALGO08.v3.short_rank_trial import summarize, traced


def test_rank_trace_surrounds_the_two_original_reductions():
    source = """static void find_times() {
    int radius = (int)nearbyint(6. / w->stride);
    emit_timing_maxima();
}

static double bin_hz() {}
void find_carriers() {
        int prev = -1;
        for (;;) {
            emit_carrier_maximum();
            prev = best;
        }
}
"""
    body = traced(source)
    assert body.index("time_rank_started =") < body.index("emit_timing_maxima()") < body.index("rank_cost[0]")
    assert body.index("carrier_rank_started =") < body.index("emit_carrier_maximum()") < body.index("rank_cost[1]")
    with pytest.raises(ValueError):
        traced(source.replace("int prev = -1", "int prev = 0"))


def test_summary_prices_whole_round_medians_and_disjoint_native_stages():
    def row(values):
        return {"runs": [{"trace": dict(cpu=n*10, wall=n*11, timing_rank=n*2, carrier_rank=n)} for n in values]}

    assert summarize([row([1, 5, 7]), row([9, 1, 1])]) == {
        "trace": {"cpu": 40, "wall": 44, "timing_rank": 8, "carrier_rank": 4}}
