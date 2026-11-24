from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import exact_named_route
from reports.ALGO08.v3.exact_named_route_score import ARMS, RECEIPT, parity


@pytest.mark.parametrize("unsupported", (False, True))
def test_named_rank_uses_the_original_finalists_and_restores_scopes(unsupported):
    active, calls, stats, work = [], [], [], Counter()
    scan, nodes = object(), [object(), object()]

    class Tables:
        def projection(self):
            raise AssertionError("Unused in this test")

    tables = Tables()
    discovery = SimpleNamespace(phase_linear_frequency=tables.projection)

    @contextmanager
    def sharing(current):
        assert current is scan
        active.append("shared")
        try:
            yield {"actual_shared_calls": 4}
        finally:
            assert active.pop() == "shared"

    @contextmanager
    def install(current, bound, counts):
        assert current is scan and bound is tables
        if unsupported:
            raise ValueError("Unsupported stock port")
        active.append("blocks")
        try:
            yield
        finally:
            assert active.pop() == "blocks"

    def original(current):
        assert current is scan
        assert active == (["shared"] if unsupported else ["shared", "blocks"])
        calls.append(current)
        return nodes

    rank = exact_named_route.rank_with_exact_inputs(original, sharing, install, discovery, stats, work)
    assert rank(scan) is nodes
    assert not active and calls == [scan]
    assert stats[0]["nodes"] == 2 and stats[0]["inputs"] == {"actual_shared_calls": 4}
    assert work["stock_curve_fallback"] == int(unsupported)


def test_transfer_gate_requires_ordered_owners_and_real_publication():
    receipt = dict.fromkeys(RECEIPT, "signed") | {"decision": "complete"}
    original = dict(worker=dict(receipt=receipt, solve={}), terminal={"state": "ok"},
                    rows={arm: [[1, 100, "conditional"], [2, 100, "predictive"]] for arm in ARMS},
                    science=dict(raw_authority="physical", arms=dict.fromkeys(ARMS, {"latlon": [0., 0.]}),
                                 scientific_digests={"path": "signed", "grid": "signed"}),
                    products=dict(images={str(i): {"sha256": str(i)} for i in range(8)}))
    assert all(parity(original, deepcopy(original)).values())
    changed = deepcopy(original)
    changed["rows"]["fitted_c"].reverse()
    changed["products"]["images"].pop("4")
    states = parity(original, changed)
    assert {name for name, equal in states.items() if not equal} == {"ordered_owners", "eight_pngs"}
