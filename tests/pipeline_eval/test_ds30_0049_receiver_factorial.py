from reports.ALGO08.v3.ds30_0049_receiver_factorial import choose, compare


def factor(cfo, epoch=500, margin=0.04, rank=0):
    return dict(fractional_tracking_cfo_hz=cfo, integer_epoch_sample=epoch,
                fractional_epoch_offset_samples=0.0, fractional_margin=margin,
                candidate_rank=rank, passed_fractional_margin_gate=True)


def test_original_anchor_and_empty_slots_are_fed_to_each_selector_history():
    a, b = factor(30_000), factor(30_100)
    rows = [dict(opportunity=dict(edge="lower"), anchor=True, alternatives={"20-two": [a], "8-primary": [b]}),
            dict(opportunity=dict(edge="lower"), anchor=False, alternatives={"8-primary": []}),
            dict(opportunity=dict(edge="lower"), anchor=False, alternatives={"8-primary": [b]})]

    class History:
        def __init__(self):
            self.seen = []

        def select(self, row):
            candidates = row["candidates"]
            keep = 0 if len(self.seen) == 2 and self.seen == [[a], []] else None
            self.seen.append(candidates)
            return None, keep, []

    assert [r["candidates"] for r in choose(rows, "8-primary", "continuation", History)] == [[], [], [b]]
    assert [r["candidates"] for r in choose(rows, "8-primary", "strongest", History)] == [[a], [], [b]]


def test_signed_cfo_and_wrapped_timing_define_matched_owner_recovery():
    baseline = factor(34_000)
    assert compare(baseline, factor(34_250, epoch=13_834)) == "matched"
    assert compare(baseline, factor(34_251)) == "displaced"
    assert compare(baseline, factor(34_000, epoch=497)) == "displaced"
    assert compare(baseline, None) == "empty"
    assert compare(None, baseline) == "gained"
