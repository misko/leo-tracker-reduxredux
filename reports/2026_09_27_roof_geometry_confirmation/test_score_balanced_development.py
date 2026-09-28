import pytest
from score_balanced_development import verify_budget


def arm():
    return dict(evaluated_points=160,trace=[dict(event='evaluate',east_km=i,north_km=0) for i in range(160)])


def test_exact_unique_budget():
    verify_budget(arm())


def test_duplicate_cannot_satisfy_declared_budget():
    value=arm(); value['trace'][-1]=value['trace'][0]
    with pytest.raises(ValueError,match='unique'): verify_budget(value)


def test_declared_budget_cannot_hide_missing_evaluations():
    value=arm(); value['trace'].pop()
    with pytest.raises(ValueError,match='unique'): verify_budget(value)
