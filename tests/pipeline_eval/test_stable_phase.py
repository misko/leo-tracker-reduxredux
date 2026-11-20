from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import stable_phase_trial
from tools.pipeline_eval.variants.stable_phase import refresh


def run(positions, phases, *, rounds=5):
    built = []

    def build(reference):
        i = len(built)
        built.append(reference.copy())
        return SimpleNamespace(
            i=i, labels=np.array([0, 1]), state=lambda x: dict(phases=np.array(phases[i]))
        )

    def fit(problem, anchor, *, iterations):
        assert iterations == 7
        np.testing.assert_array_equal(anchor, positions[problem.i - 1] if problem.i else [0, 0])
        return dict(parameters=positions[problem.i])

    return refresh(build, fit, np.zeros(2), rounds=rounds, iterations=7), built


def test_requires_both_stability_conditions_and_returns_the_last_actual_model():
    pos = [[0.1, 0.0], [0.1011, 0.0], [0.1012, 0.0], [0.10119, 0.0]]
    phases = [[2, -2], [2.001, -2.001], [2.1, -2.001], [2.101, -2.0009]]
    (p, fit, history), refs = run(pos, phases)
    assert p.i == 3 and fit["parameters"] == pos[-1]
    assert len(history) == 4
    np.testing.assert_array_equal(refs[-1], phases[-2])
    np.testing.assert_array_equal(history[-1]["posterior_phase_s"], phases[-1])


def test_unclipped_orbit_at_limit_cannot_be_misclassified_as_converged():
    (_, _, history), refs = run([[0, 0]] * 5, [[20.0, 0.0]] * 5)
    assert len(history) == 5 and all(h["max_reference_change_s"] >= 5 for h in history)
    assert all(r[0] == 15 for r in refs[1:])
    (_, _, single), _ = run([[0, 0]], [[0, 0]], rounds=1)
    assert len(single) == 1
    with pytest.raises(ValueError, match="positive"):
        run([], [], rounds=0)


def test_roster_is_hash_fixed_counterbalanced_and_has_distinct_confirmations():
    cases = [f"DS26-{j:04d}" for j in range(12)] + [f"DS29-{j:04d}" for j in range(8)]
    a = stable_phase_trial.schedule(cases)
    assert a == stable_phase_trial.schedule(reversed(cases))
    jobs = [pair for lane in a.values() for pair in lane]
    assert len(set(ident for ident, _ in jobs)) == 6
    assert [p[1] for p in a["11"][:2]] == [stable_phase_trial.METHOD, stable_phase_trial.STOCK]
    assert [p[1] for p in a["19"][:2]] == [stable_phase_trial.STOCK, stable_phase_trial.METHOD]
