from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.live_orbit_support import bind


@pytest.mark.parametrize("extended,policy,expected", [
    (0, "stock", "stock"),
    (1, "stock", "orbit_support"),
    (1, "history_support", "history_support"),
    (0, "orbit_support", "orbit_support"),
])
def test_only_actual_extension_interprets_the_stock_policy(extended, policy, expected):
    calls = []
    result, packet = object(), object()

    def solve(arg):
        calls.append(arg)
        return result, packet, policy

    @contextmanager
    def support():
        yield {"corner_projections_extended": extended}

    position = SimpleNamespace(solve=solve)
    scanner = SimpleNamespace(solve=solve)
    audit = []
    with bind(position, scanner, support, audit):
        assert scanner.solve is position.solve
        assert scanner.solve("original argument") == (result, packet, expected)
    assert scanner.solve is position.solve is solve
    assert calls == ["original argument"]
    assert audit == [{"corner_projections_extended": extended}]


def test_unknown_error_is_raised_with_both_original_aliases_restored():
    denial = ValueError("Invalid orbital seam")

    def solve():
        raise denial

    @contextmanager
    def support():
        yield {"corner_projections_extended": 0}

    position = SimpleNamespace(solve=solve)
    scanner = SimpleNamespace(solve=solve)
    audit = []
    with pytest.raises(ValueError) as caught, bind(position, scanner, support, audit):
        scanner.solve()
    assert caught.value is denial
    assert scanner.solve is position.solve is solve
