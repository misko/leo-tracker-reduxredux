import benchmark_algo07v3_position_geometry as benchmark
import pytest

from leo.analysis.localization_v3 import marginal


@pytest.mark.parametrize('fail', [False, True])
def test_calculator_is_restored_after_trial_or_error(fail):
    original = marginal.JointMarginal.calculate
    marker = object()
    try:
        with benchmark.calculator(marker):
            assert marginal.JointMarginal.calculate is marker
            if fail:
                raise RuntimeError('fit failed')
    except RuntimeError:
        assert fail
    assert marginal.JointMarginal.calculate is original


def test_alternating_fits_match_each_arm_across_all_three_pairs():
    calls = []

    def run(arm, side):
        calls.append((arm, side))
        return dict(seconds=1., cpu_seconds=0.5, signature=arm)

    rows = benchmark.alternating_fits(run)
    assert len(rows) == 12
    order = ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    assert calls == [(arm, side) for arm in ('c0', 'fitted_c') for side in order]


def test_changed_full_fit_cannot_emit_a_successful_comparison():
    with pytest.raises(ValueError, match='Full phase-refreshed fit changed'):
        benchmark.alternating_fits(lambda arm, side: dict(signature=side))
