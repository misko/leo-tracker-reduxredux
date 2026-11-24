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
