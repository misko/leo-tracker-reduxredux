from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    root = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(root))
    return import_module("north_fallback_overlap")


def test_numeric_fingerprint_preserves_bits_types_shape_and_order(audit):
    assert audit.fingerprint(np.array([0.0])) != audit.fingerprint(np.array([-0.0]))
    assert audit.fingerprint(np.ones((1, 2))) != audit.fingerprint(np.ones(2))
    assert audit.fingerprint(np.ones(2, dtype="f8")) != audit.fingerprint(np.ones(2, dtype="f4"))
    assert audit.fingerprint([("row", 2), ("alias", -1)]) != audit.fingerprint([("alias", -1), ("row", 2)])
    assert audit.fingerprint(np.ones((0, 2))) == audit.fingerprint(np.ones((0, 2)))


def test_fallback_requires_earlier_phase_exact_answer(audit):
    watch = audit.Watch()
    key = watch.identity(object()), "region"
    with watch.scoped("phase", "candidate"):
        assert watch.operation("project", key, 1, lambda: [0.0]) == [0.0]
    with watch.scoped("phase", "fallback"):
        watch.operation("project", key, 1, lambda: [-0.0])
        watch.operation("project", key, 1, lambda: [0.0])
        watch.operation("project", None, 1, lambda: [0.0])
        watch.operation("object", key, 1, object)
    original, unequal, equal, unknown, unsupported = watch.report()
    assert original["key"] == ["object_1", "region"]
    assert unequal["earlier_phases"] == ["candidate"] and unequal["matches"] == []
    assert equal["matches"] == ["candidate"]
    assert "matches" not in unknown and "matches" not in unsupported
    assert watch.phase == "early_regional"


def test_grid_readback_ignores_only_its_clock(audit):
    grid = {"elapsed_seconds": 1.0, "points": [0.0], "binding": {"input": "sha256:a"}}
    assert audit.numerical_grid(grid) == audit.numerical_grid(dict(grid, elapsed_seconds=2.0))
    assert audit.numerical_grid(grid) != audit.numerical_grid(dict(grid, points=[1.0]))


def test_price_disjoint_matches_and_charge_key_cost_for_both_phases(audit):
    def operation(name, phase, *, match=False, nested=False):
        return dict(operation=name, phase=phase, nested_rank=nested, operation_cpu_ns=1000,
                    key_cpu_ns=10, matches=["candidate"] if match else [])

    rows = [operation("ranked_initial_nodes", "candidate"), operation("ranked_initial_nodes", "fallback", match=True),
            operation("nominal_discovery_projection", "fallback", match=True, nested=True),
            operation("scan_context", "fallback"), operation("terminal_regional_proof", "fallback")]
    price = audit.priced_overlap(rows)
    assert price["ranked_initial_nodes"]["keys_cpu_s"] == 20e-9
    assert price["nominal_discovery_projection"]["gross_cpu_s"] == 0
    assert price["scope_ceiling_s"] == pytest.approx(960e-9)
    assert price["opaque_context_inclusive_cpu_s"] == 1000e-9
