import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

spec = importlib.util.spec_from_file_location('age_profile_fit', Path(__file__).with_name('fit.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_constructor_and_continuation_share_one_actual_objective_budget():
    calls = []
    def objective(v, n):
        calls.append(1)
        return 0., np.zeros_like(v), np.zeros_like(n), None
    ctx = SimpleNamespace(vector=np.zeros(9), nuisance=np.zeros(1), fixed_c=False,
                          model=SimpleNamespace(evaluate_joint=objective))
    class Profile:
        def __init__(self, context, v, n):
            self.initial_objective = context.model.evaluate_joint(v, n)[0]
            self.projections = 0
        def search(self, **kwargs):
            return []
    def refitter(context, v, n, **options):
        for _ in range(options['max_evaluations']):
            context.model.evaluate_joint(v, n)
        return dict(vector=v, nuisance=n, diagnostics=dict(objective=0.,
                    evaluations=options['max_evaluations']))
    result = module.fit(ctx, profile_factory=Profile, refitter=refitter,
                        max_evaluations=1000, max_seconds=2)
    assert result['diagnostics']['evaluations'] == len(calls) == 1000
    assert len(result['diagnostics']['rounds']) == 2
