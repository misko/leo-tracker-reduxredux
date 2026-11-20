import numpy as np

from tools.pipeline_eval.variants.v5_phase_cache import MAX_INPUT, NormalMemo


class Backend:
    def __init__(self):
        self.calls = 0

    def calculate(self, raw, design, *, powers):
        self.calls += 1
        return {"coefficient": raw + design.sum(axis=0) + powers}


def test_one_entry_is_exact_and_never_shares_mutable_results():
    backend = Backend()
    memo = NormalMemo()
    design = np.asfortranarray(np.arange(6.0).reshape(3, 2))
    raw = np.array([0.0, 1.0])
    powers = np.ones(2)

    def run():
        return memo.solve(Backend.calculate, backend, raw, design, powers=powers)

    first = run()
    expected = first["coefficient"].copy()
    first["coefficient"] *= 0
    np.testing.assert_array_equal(run()["coefficient"], expected)
    assert backend.calls == 1
    raw[0] = -0.0
    run()
    assert backend.calls == 2
    design[0, 1] += 1.0
    run()
    assert backend.calls == 3
    design = np.array(design, order="C")
    run()
    assert backend.calls == 4
    backend = Backend()
    np.testing.assert_array_equal(run()["coefficient"], expected + [0.0, 1.0])
    assert backend.calls == 1


def test_oversize_and_unusual_views_always_reach_the_original():
    class Bound:
        calls = 0

        def calculate(self, values):
            self.calls += 1
            return {"size": len(values)}

    memo = NormalMemo()
    backend = Bound()
    for values in (np.zeros(1 + MAX_INPUT // 8), np.zeros(20)[::2]):
        assert memo.solve(Bound.calculate, backend, values) == {"size": len(values)}
        memo.solve(Bound.calculate, backend, values)
    assert backend.calls == 4
    assert memo.entry is None
