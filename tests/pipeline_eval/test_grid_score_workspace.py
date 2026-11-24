from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from grid_score_workspace import Workspace, build, released_cache, scalar_grid_score


def problems():
    from leo.analysis.localization_v3.event_position import cached

    stored = []
    p = {a: SimpleNamespace(keep=np.array([True])) for a in ("c0", "fitted_c")}
    points = {"c0": [0., 0.], "fitted_c": [1., 1.]}
    for arm, problem in p.items():
        def calculate(x, arm=arm):
            result = dict(negative_twice_elbo=float(x @ x), elevation=np.array([0.]), features=np.asarray(x).copy())
            stored.append((arm, x, result))
            return result

        problem.calculate = calculate
        cached(problem)
        problem.calculate(points[arm])
    return stored, points, p, dict(problems={a: (p[a], points[a]) for a in p}, families=[])


def test_only_unique_scalar_nodes_bypass_retained_original_endpoint_records():
    from leo.analysis.position_grid import sample_position_grid
    from leo.analysis.localization_v3 import event_position

    stored, endpoints, p, context = problems()
    workspace = SimpleNamespace(owner=None)
    with scalar_grid_score(sample_position_grid, context, endpoints, workspace) as (score, counters, audit):
        assert audit == {"admitted": 1}
        for arm in p:
            own = released_cache(p[arm], event_position)
            assert score(arm, endpoints[arm]) == (0. if arm == "c0" else 2.)
            assert score(arm, [2., 3.]) == 13.
            assert own.cache_info().currsize == 1 and own.cache_info().hits == 1
            assert score(arm, [2., 3.]) == score(arm, [2., 3.]) == 13.
            assert own.cache_info().currsize == 2 and own.cache_info().hits == 2
            assert counters[arm] == {"scalar_only": 1, "ordinary": 3}
    assert len(stored) == 6 and workspace.owner is None


def test_ordinary_route_is_used_with_unknown_sampler_or_batch():
    from leo.analysis.position_grid import sample_position_grid

    for sampler, mapper in ((lambda: None, None), (sample_position_grid, lambda: None)):
        _, endpoints, _, context = problems()
        workspace = SimpleNamespace(owner=None)
        with scalar_grid_score(sampler, context, endpoints, workspace, map_batches=mapper) as (score, counters, audit):
            assert score("c0", [2., 3.]) == 13. and not audit and not counters["c0"]


def stock_assemble(p, f, h, m, scale, geometry_only):
    def direct_features(problem, derivative, modes, scales):
        result = np.column_stack((problem.hardware, problem.smooth, np.zeros((len(f), 2 + 3))))
        phase = 2 + problem.flat_labels
        row = np.arange(len(f))
        result[row, phase] = (problem.q * derivative) * problem.phase_sigma[problem.flat_labels]
        supported = problem.flat_labels == 1
        result[supported, 4:] = problem.q[supported, None] * modes[supported]
        return result

    use_direct = geometry_only
    problem, derivative, modes, scales = p, h, m, scale
    result = (direct_features(problem, derivative, modes, scales) if use_direct else None)
    return result


@pytest.mark.hardware
def test_in_place_native_updates_are_bit_identical_and_owned_mode_remains_private(tmp_path):
    binary = tmp_path/"workspace.so"
    build(binary)
    work = Workspace(binary)
    p = SimpleNamespace(variant="radio_noise", hardware=np.ones((3, 1)), smooth=np.ones((3, 1)),
                        constants=np.empty((3, 0)), q=np.array([1.1, .95, 1.2]), labels=[0, 1],
                        flat_labels=np.array([0, 1, 1]), phase_sigma=np.array([5., 3.]), supported_local=[1])
    originals = {"_assemble": stock_assemble}
    steps = [np.array([-.1, .03, .6]), np.array([.09, -.02, .55]), np.array([2.2, -8., -.7])]
    arguments = [(p, np.ones(3), step, np.column_stack((step, -step, step[::-1])), np.ones(3), True)
                 for step in steps]
    with work.binding(originals):
        work.owner = p
        first = originals["_assemble"](*arguments[0])
        assert first.tobytes() == stock_assemble(*arguments[0]).tobytes()
        second = originals["_assemble"](*arguments[1])
        assert second is first and second.tobytes() == stock_assemble(*arguments[1]).tobytes()
        work.owner = None
        third = originals["_assemble"](*arguments[2])
        assert third is not second and third.tobytes() == stock_assemble(*arguments[2]).tobytes()
    assert work.counts["borrowed_designs"] == 2 and originals["_assemble"] is stock_assemble
