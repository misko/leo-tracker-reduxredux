import pytest

from tools.pipeline_eval.variants import selective_capture as study


def peak(margin, rank=0, epoch=710, cfo=17_000):
    return dict(
        candidate_rank=rank,
        integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=0.27,
        fractional_tracking_cfo_hz=cfo,
        fractional_margin=margin,
        passed_fractional_margin_gate=margin >= study.MARGIN,
    )


def pair(visit, factors):
    return [
        dict(visit_index=visit, receiver_id=rx, candidates=factors if rx == 0 else [])
        for rx in range(2)
    ]


def test_wide_eligibility_ignores_empty_and_aliased_duplicates():
    assert study.trigger(pair(1, [])) is None
    assert study.trigger(pair(1, [peak(0.0124)])) is None
    assert study.trigger(pair(1, [peak(0.0125)]))["reason"] == "near_gate"
    aliased = peak(0.028, rank=2, cfo=17_000 + study.ALIAS)
    assert study.trigger(pair(1, [peak(0.033), aliased])) is None
    assert (
        study.trigger(pair(1, [peak(0.033), peak(0.029, rank=2, epoch=717)]))["reason"]
        == "competing_branch"
    )


def test_budget_is_hard_on_every_prefix_and_uniform_matches_count():
    visits = [p for i in range(289) for p in pair(2 * i, [peak(0.021)] if i % 3 == 0 else [])]
    full = study.schedule(visits)
    for width in study.BUDGETS:
        phase = full["policies"][f"first_{width}"]
        assert all(i["admitted_index"] >= width for i in phase)
        assert len(phase) == len(full["policies"][f"uniform_{width}"])
        assert len({r["block"] for r in phase}) == len(phase)
        for n in range(0, 290, 5):
            prefix = study.schedule(visits[: 2 * n])["policies"][f"first_{width}"]
            assert prefix == [r for r in phase if r["admitted_index"] < n]
            assert len(prefix) <= n // width


def test_mix_keeps_physical_stereo_and_rejects_missing_selected_visits():
    wide = pair(1, []) + pair(8, [peak(0.024)])
    captured = pair(1, [peak(0.044)]) + pair(8, [])
    assert study.mix_probes(wide, captured, {8}) == wide[:2] + captured[2:]
    with pytest.raises(ValueError, match="missing or invalid"):
        study.mix_probes(wide, captured, {3})
    with pytest.raises(ValueError, match="stereo"):
        tuple(study.visit_pairs(wide[:-1]))
