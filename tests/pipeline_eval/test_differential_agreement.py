from tools.pipeline_eval.qualification import differential_agreement as study


def peak(time, hz, rank=0, margin=1, gated=True):
    return dict(
        integer_epoch_sample=int(time),
        fractional_epoch_offset_samples=time % 1,
        fractional_tracking_cfo_hz=hz,
        passed_fractional_margin_gate=gated,
        fractional_margin=margin,
        candidate_rank=rank,
    )


def test_new_win_can_match_an_alternative_without_matching_capture_winner():
    first = peak(5500, 10_000)
    other = peak(9000, -21_000, rank=1, margin=0.2)
    row = study.classify(None, other, [first, other], 13_333)
    assert row["transition"] == "gained"
    assert row["hinted"] == "other_capture_candidate"
    assert not row["hinted_absolute"]


def test_frame_wrap_and_frequency_alias_keep_the_same_physical_family():
    current = peak(13_332.8, study.factor_cross.ALIAS_HZ + 600)
    reference = peak(0.1, 500)
    row = study.classify(reference, current, [reference], 13_333)
    assert row["transition"] == "same_family"
    assert row["stock_absolute"] and not row["hinted_absolute"]
    assert row["hinted"] == "capture_winner"


def test_lost_positive_and_absent_reference_keep_distinct_denominators():
    kept = peak(82, 10)
    rows = [
        dict(id=study.CASES[0], **study.classify(kept, None, [kept], 13_333)),
        dict(id=study.CASES[1], **study.classify(None, kept, [peak(82, 10, gated=False)], 13_333)),
    ]
    pooled = study.summary(rows)["pooled"]
    assert pooled["probes"] == 2 and pooled["capture_positive"] == 1
    assert pooled["losses_by_stock_label"] == {"capture_winner": 1}
    assert pooled["gains_by_hint_label"] == {"capture_negative": 1}
