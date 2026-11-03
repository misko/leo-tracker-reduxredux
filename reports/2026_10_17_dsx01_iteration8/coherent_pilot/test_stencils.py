import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "coherent_stencils", Path(__file__).with_name("stencils.py")
)
stencils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stencils)


def test_central_and_feasible_second_order_boundary_match_quadratic():
    def f(x):
        return 7.0 + 3 * x + 2 * x * x

    for valid in (lambda x: abs(x) < 1e-3, lambda x: x >= 0, lambda x: x <= 0):
        rule = stencils.choose(valid)
        value = stencils.finite_difference(f(0), [f(x) for x in rule["offsets"]], rule)
        assert abs(value - 3.0) < 1e-8
    assert stencils.choose(lambda x: x >= 0)["kind"] == "one-sided-source-cell"


def test_source_cell_is_checked_at_both_one_sided_points():
    rule = stencils.choose(lambda x: 0 <= x <= 1.5e-5)
    assert abs(rule["h"]) == 1e-6
    with pytest.raises(ValueError, match="direction not omitted"):
        stencils.choose(lambda x: False)
