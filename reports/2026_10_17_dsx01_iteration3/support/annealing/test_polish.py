import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('annealing_polish',
                                             Path(__file__).with_name('polish.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_uniform_policy_respects_remaining_calls_and_active_time():
    d = dict(evaluations=871, elapsed_seconds=23.64)
    assert module.allowance(d, dict(accepted=False, feasible=True)) == (129, 78.)
    assert module.allowance(dict(evaluations=900, elapsed_seconds=110),
                            dict(accepted=False, feasible=True)) == (100, 10.)
    assert module.allowance(d, dict(accepted=True, feasible=True)) is None
    assert module.allowance(d, dict(accepted=False, feasible=False)) is None
    assert module.allowance(dict(evaluations=1000, elapsed_seconds=1),
                            dict(accepted=False, feasible=True)) is None
    assert module.allowance(dict(evaluations=1, elapsed_seconds=120),
                            dict(accepted=False, feasible=True)) is None
