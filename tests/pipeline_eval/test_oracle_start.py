from tools.pipeline_eval.qualification import oracle_start


def candidate(epoch, cfo, margin=0.1, rank=0):
    return dict(
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.0,
        fractional_tracking_cfo_hz=cfo,
        fractional_margin=margin,
        passed_fractional_margin_gate=margin >= 0.025,
        candidate_rank=rank,
    )


def test_matching_uses_circular_epoch_and_reports_literal_cfo_separately():
    target = candidate(0, 16000)
    aliased = candidate(13332, 16000 + oracle_start.ALIAS_HZ)
    assert oracle_start.target_matches(aliased, target)
    assert not oracle_start.target_matches(aliased, target, exact_cfo=True)
    assert not oracle_start.target_matches(candidate(13330, 16000), target)


def test_conditional_gate_and_margin_winner_are_distinct():
    target = candidate(140, 32000)
    below = candidate(140, 32000, margin=0.024, rank=2)
    other = candidate(500, -70000, margin=0.4, rank=0)
    public = dict(candidates=[{"epoch": 140}, {"epoch": 500}])
    answer = oracle_start.endpoints(target, dict(candidates=[other, below]), public)
    assert answer["status"] == "below_gate" and answer["physical_available"]
    assert not answer["passes"] and not answer["winner"]
    completed = candidate(140, 32000, margin=0.2, rank=2)
    answer = oracle_start.endpoints(target, dict(candidates=[other, completed]), public)
    assert answer["passes"] and answer["physical_passes"] and not answer["winner"]
    mismatch = candidate(140, 37000)
    assert (
        oracle_start.endpoints(target, dict(candidates=[mismatch]), public)["status"]
        == "cfo_mismatch"
    )


def test_pick_deduplicates_visits_and_allocates_original_margin_strata():
    entry = lambda v, rx, k, s: dict(visit=v, receiver=rx, kind=k, stratum=s)  # noqa: E731
    inputs = [
        entry(0, 0, "matched", "strong"),
        entry(1, 0, "miss", "weak"),
        entry(1, 1, "miss", "middle"),
        entry(2, 0, "miss", "strong"),
        entry(3, 0, "matched", "strong"),
        entry(4, 1, "miss", "middle"),
        entry(5, 0, "miss", "strong"),
        entry(6, 1, "matched", "strong"),
    ]
    output = oracle_start.choose(inputs)
    assert [row["visit"] for row in output] == [0, 1, 2, 4, 5, 6]
