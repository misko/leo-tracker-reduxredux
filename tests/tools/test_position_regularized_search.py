import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "tools/research/position_regularized_search.py"
    spec = importlib.util.spec_from_file_location("regularized_search_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fit_window_uses_training_objective_only():
    module = _module()

    class Training:
        @staticmethod
        def bounded_fit(objective, seed, max_evaluations):
            return {
                "latitude_deg": seed[0],
                "longitude_deg": seed[1],
                "training_rmse_hz": objective(seed),
                "evaluations": 1,
            }

    class Timing:
        pass

    class Joint:
        pass

    module.score_location = lambda *args, **kwargs: args[4][0]  # objective depends on point only
    fits, selected = module.fit_window(
        Training(), Joint(), Timing(), {}, ["s"], [[2, 0], [1, 0]], 2, {}
    )
    assert len(fits) == 2
    assert selected["latitude_deg"] == 1
