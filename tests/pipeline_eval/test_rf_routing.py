import pytest

from tools.pipeline_eval.variants.rf_routing import choose_rf


def test_assignment_uses_a_fixed_seed_and_physical_frequency_only():
    seed = "26" * 32
    centers = [11_280_000_000, 11_530_000_000, 11_780_000_000]
    assert choose_rf(seed, centers) == choose_rf("sha256:" + seed, reversed(centers))
    assert choose_rf(seed, centers) == choose_rf(seed, [*map(float, centers), centers[0]])
    assert choose_rf("AB" * 32, centers) == choose_rf("ab" * 32, centers)
    assert choose_rf(seed, [centers[2]]) == centers[2]


@pytest.mark.parametrize("bad", [[], [False], [0], [-1], [10.5], [float("nan")], ["10"]])
def test_unusable_physical_plan_is_rejected(bad):
    with pytest.raises(ValueError):
        choose_rf("ab" * 32, bad)
    with pytest.raises(ValueError, match="seed"):
        choose_rf("roof", [100])
