from reports.ALGO08.v3.short_signed_trial import ARM_NAMES, FRAMES, SAMPLES, geometry, match, summarize


def factor(rank, epoch, offset, hz):
    return rank, epoch, offset, hz, 0.9, 0.15


def test_eight_origins_include_the_latest_confirmation_and_verifier_stencil():
    shape = geometry()
    assert FRAMES == 8
    assert SAMPLES == shape["sample_rate_hz"] * 12 // 1000
    assert shape["last_origin"] == 93333
    assert shape["first_unused_latest_confirmation_sample"] == 119777
    assert all(value < SAMPLES for field, value in shape.items() if field.startswith("first_unused"))


def test_matching_wraps_epoch_and_preserves_signed_carriers_and_ranks():
    left = factor(0, 13332, 0.2, -300)
    near = factor(0, 0, 0.2, -200)
    opposite = factor(0, 0, 0, 200)
    swapped = factor(1, 0, 0, -200)
    assert match([left], [near], ranks=True) == [(0, 0, 1, 100)]
    assert not match([left], [opposite], ranks=False)
    assert not match([left], [swapped], ranks=True)
    assert match([left], [swapped], ranks=False)


def test_fallback_charges_all_lanes_with_missing_factors_even_when_short_returns_one():
    a, b = factor(0, 6, 0, -6000), factor(1, 543, 0, 2000)
    full = [a, b]
    rows = [
        dict(factors=dict(installed=stock, control=stock, short=short),
             selection=dict.fromkeys(ARM_NAMES),
             cpu_ns=dict(installed=[1000], control=[1000], short=[400]),
             wall_ns=dict(installed=[1000], control=[1000], short=[400]))
        for stock, short in ((full, [a]), ([a], []), ([], []), ([a], [a]))
    ]
    result = summarize(rows)
    assert result["by_rank"]["matched"] == [2, 0]
    assert result["counts"]["short_nonempty_mismatch"] == 1
    assert result["counts"]["empty_lost_stock"] == 1
    assert result["cpu"]["oracle_fallback"]["total_s"] == [3600 / 1e9]
    assert result["cpu"]["empty_fallback"]["total_s"] == [3600 / 1e9]
