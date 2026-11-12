"""Structural proof that the probe changes only the declared position start."""

import ast
import inspect

import numpy as np
import pytest
from probe_algo07v5_joint_start import initialized_fit

from leo.analysis.localization_v3 import joint_recovery


@pytest.mark.parametrize('name', ['_fit_lbfgsb', '_fit_powell'])
def test_only_position_start_and_keyword_are_changed(name):
    function = getattr(joint_recovery, name)
    transformed, original, changed = initialized_fit(function)
    before, after = ast.parse(original), ast.parse(changed)
    definition = after.body[0]
    assert [k.arg for k in definition.args.kwonlyargs] == ['start']
    assert definition.args.kw_defaults == [None]
    assignment, = [node for node in definition.body if isinstance(node, ast.Assign)
                   and ast.unparse(node.targets[0]) == 'x']
    assert ast.unparse(assignment.value) == 'np.array(start, dtype=float, copy=True)'
    assignment.value = ast.parse('np.zeros(2)', mode='eval').body
    definition.args.kwonlyargs.clear()
    definition.args.kw_defaults.clear()
    assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
    assert inspect.signature(transformed).parameters['start'].kind.name == 'KEYWORD_ONLY'


@pytest.mark.parametrize('name', ['_fit_lbfgsb', '_fit_powell'])
def test_zero_start_bits_and_warm_copy(name):
    _, _, changed = initialized_fit(getattr(joint_recovery, name))
    definition = ast.parse(changed).body[0]
    assignment, = [node for node in definition.body if isinstance(node, ast.Assign)
                   and ast.unparse(node.targets[0]) == 'x']
    expression = compile(ast.Expression(body=assignment.value), '<start>', 'eval')
    zero = eval(expression, {'np': np, 'start': [0, 0]})
    assert zero.dtype == np.float64
    assert zero.tobytes() == np.zeros(2).tobytes()
    start = np.array([1.25, -2.0])
    warm = eval(expression, {'np': np, 'start': start})
    np.testing.assert_array_equal(warm, start)
    warm[0] = 99
    assert start[0] == 1.25


@pytest.mark.parametrize(('old', 'new'), [
    ('x = np.zeros(2)', 'x = np.zeros(3)'),
    ('range(5)', 'range(4)'),
    ('maxiter=48', 'maxiter=24'),
    ('maxfun=240', 'maxfun=120'),
])
def test_changed_scientific_boundary_is_rejected(monkeypatch, old, new):
    source = inspect.getsource(joint_recovery._fit_lbfgsb)
    assert old in source
    monkeypatch.setattr(inspect, 'getsource', lambda function: source.replace(old, new))
    with pytest.raises(ValueError):
        initialized_fit(joint_recovery._fit_lbfgsb)
