from types import SimpleNamespace

from ports import dependencies
from search import search_slice


def test_fresh_two_queues_share_native_fit_and_durable_bootstrap(tmp_path, monkeypatch):
    _, driver, _ = dependencies()
    monkeypatch.setattr(driver, "case_identity", lambda case: {"fixed": "synthetic"})
    case = dict(observations=None, bank=None, prior=SimpleNamespace(radius_km=240.0), tracks=None)
    calls, seeds = [], []

    class Evaluator:
        def __init__(self, *args):
            self.seeds = {}

        def bootstrap(self, obs, bank, prior, point, tracks, **kwargs):
            seeds.append(point)
            return driver.PositionBootstrap((0, 1), driver.np.array([*point, *([0.0] * 7)]), ())

        def __call__(self, e, n, arm):
            assert arm == "fitted-c" and (e, n) in self.seeds
            calls.append((e, n))
            return dict(
                fit=dict(converged=True),
                scores=dict(
                    native=dict(objective=e**2 + n**2),
                    fixed=dict(objective=(e - 80.0) ** 2 + (n + 80.0) ** 2),
                ),
            )

    plan, member = {}, dict(label="synthetic", binding={})
    result = search_slice(
        plan, member, tmp_path, lambda binding: case, driver, evaluator_factory=Evaluator
    )
    assert result["status"] == "complete" and set(result["searches"]) == {"native", "fixed"}
    assert all(len(row["search"]["evaluations"]) == 400 for row in result["searches"].values())
    assert len(calls) == len(set(calls)) == len(seeds)
    assert 400 <= len(calls) <= 800
    assert all(len(row["regions"]) == 3 for row in result["searches"].values())
    before = len(calls)
    assert (
        search_slice(
            plan, member, tmp_path, lambda binding: case, driver, evaluator_factory=Evaluator
        )
        == result
    )
    assert len(calls) == before
