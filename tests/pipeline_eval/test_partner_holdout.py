import pytest

from tools.pipeline_eval.qualification.partner_holdout import split


def test_holdout_is_exact_complement_of_the_frozen_discovery():
    eligible = [f"case-{i:02d}" for i in range(22)]
    discovery = eligible[::3]
    held, pooled = split(eligible[::-1], discovery)
    assert len(held) == 14 and len(pooled) == 22
    assert not set(held) & set(discovery)
    assert pooled == eligible
    assert set(held) | set(discovery) == set(pooled)


def test_bad_or_duplicate_discovery_cannot_shrink_holdout_denominator():
    eligible = list(range(22))
    with pytest.raises(ValueError, match="contained"):
        split(eligible, list(range(7)) + [999])
    with pytest.raises(ValueError, match="unique"):
        split(eligible, [*range(7), 0])
    with pytest.raises(ValueError, match="unique"):
        split(eligible[:-1], list(range(8)))
