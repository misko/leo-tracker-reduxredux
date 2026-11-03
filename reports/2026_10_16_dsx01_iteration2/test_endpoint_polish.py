import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('endpoint_polish', Path(__file__).with_name(
    'endpoint_polish.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def test_quadratic_improves_with_exact_model_call_accounting():
    calls = []
    def evaluate(point):
        calls.append(point.copy())
        return float(point@point), 2*point
    result = core.solve(evaluate, np.array([.2, -.3]), [-1, -1], [1, 1],
                        lambda p: np.linalg.norm(p) <= 1, maximum=20, seconds=2)
    assert result['objective'] < 1e-12
    assert result['diagnostics']['evaluations'] == len(calls) <= 20
    np.testing.assert_array_equal(calls[0], [.2, -.3])


def test_budget_exact_and_infeasible_calls_never_reach_model():
    calls = []
    def evaluate(point):
        assert point[0] >= 0
        calls.append(point.copy())
        return float((point[0]+1)**2), np.array([2*(point[0]+1)])
    result = core.solve(evaluate, np.array([.01]), [-2], [2],
                        lambda p: p[0] >= 0, maximum=8, seconds=2)
    assert result['point'][0] >= 0 and result['objective'] <= 1.0201
    assert result['diagnostics']['invalid_points_excluded'] > 0
    assert result['diagnostics']['attempted_chart_calls'] <= 8
    assert result['diagnostics']['evaluations'] == len(calls)
    one = core.solve(evaluate, np.array([.01]), [-2], [2],
                     lambda p: p[0] >= 0, maximum=1, seconds=2)
    assert one['diagnostics']['evaluations'] == 1
    np.testing.assert_array_equal(one['point'], [.01])


def test_invalid_raw_endpoint_and_budget_fail_before_model():
    def forbidden(*args):
        pytest.fail('must not evaluate')
    with pytest.raises(ValueError, match='raw endpoint'):
        core.solve(forbidden, np.array([-1.]), [-2], [2], lambda p: p[0] >= 0)
    with pytest.raises(ValueError, match='bounded'):
        core.solve(forbidden, np.zeros(1), [-2], [2], lambda p: True, maximum=135)
