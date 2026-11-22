from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_likelihood_reuse as cache


def test_complete_byte_comparison_and_fresh_output_after_mutation():
    raw = np.arange(8., dtype=float)
    design = np.arange(24., dtype=float).reshape(8, 3)
    arrays, types = cache.ordinary_arrays((raw, design, 1., None))
    signature = cache.small_signature(arrays)
    key = types + signature
    old = dict(coefficient=np.array([1., 3.]))
    memo = cache.Memo(8192)
    memo.insert(key, arrays, old)
    old["coefficient"][:] = 88.
    result = memo.lookup(key, arrays)
    np.testing.assert_array_equal(result["coefficient"], [1., 3.])
    result["coefficient"][:] = -2.
    np.testing.assert_array_equal(memo.lookup(key, arrays)["coefficient"], [1., 3.])

    # This value lies outside the cheap hint. The stored complete bytes still exclude a hit.
    design[1, 1] = 55.
    assert cache.small_signature(arrays) == signature
    assert memo.lookup(key, arrays) is None
    assert memo.counts["hint_collisions"] == 1


def test_payload_limit_evicts_witnesses_and_results_together():
    rows = (np.arange(4., dtype=float),)
    result = dict(coefficient=np.ones(2))
    memo = cache.Memo(64)
    memo.insert("first", rows, result)
    memo.insert("second", rows, result)
    memo.insert("too-large", (np.arange(8., dtype=float),), result)
    assert list(memo.entries) == ["second"]
    assert memo.bytes == memo.counts["peak_bytes"] == 48


def test_scope_distinguishes_conditioning_and_bypasses_grid(monkeypatch):
    calls = []

    def released(owner, *args, **options):
        calls.append(owner.min_rcond)
        return dict(coefficient=np.array([owner.min_rcond]))

    monkeypatch.setattr(native_bound.NativeBound, "__call__", released)
    monkeypatch.setattr(cache.handoff, "grid_handoff", lambda *args: nullcontext())

    class Owner(SimpleNamespace):
        __hash__ = object.__hash__

    owner = Owner(run=released, original=released, min_rcond=1e-12, counts={"fallback_memory": 0})
    grid = [False]
    args = (np.arange(8., dtype=float), np.ones((8, 3)), 5., np.arange(8, dtype=np.int64))
    with (
        cache.ordinary_likelihood_reuse() as counts,
        cache.handoff.grid_handoff(None, None, lambda: grid[0]),
    ):
        first = native_bound.NativeBound.__call__(owner, *args)
        second = native_bound.NativeBound.__call__(owner, *args)
        np.testing.assert_array_equal(first["coefficient"], second["coefficient"])
        assert len(calls) == counts["hits"] == 1
        owner.min_rcond = 1e-9
        native_bound.NativeBound.__call__(owner, *args)
        grid[0] = True
        native_bound.NativeBound.__call__(owner, *args)
    assert calls == [1e-12, 1e-9, 1e-9]
    assert counts["grid_bypasses"] == 1
