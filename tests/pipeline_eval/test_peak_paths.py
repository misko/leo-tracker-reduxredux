import numpy as np

from tools.pipeline_eval.variants import peak_paths as method


def test_wrapped_synthetic_path_survives_two_missed_visits():
    t = np.arange(44, dtype=float) * 0.71
    motion = 103000 + 850 * t + 51 * t * t
    planted = t > 2
    planted[[14, 15]] = False
    y = np.zeros((len(t), method.PEAKS))
    y[:, 0] = np.random.default_rng(91).uniform(-method.PERIOD / 2, method.PERIOD / 2, len(t))
    y[:, 2] = method.fold(motion + 2340)
    marks = np.full_like(y, -np.inf)
    marks[:, 0] = 1.9
    marks[planted, 2] = 1.3
    lane = method.Lane((0, 2, 11.4e9), np.arange(len(t)), t, y, marks)
    cost, path = method.decode(lane, np.array([motion, motion + 5500 * t]))
    assert cost[0] > cost[1]
    assert np.count_nonzero(path[0] == 2) >= planted.sum() - 1
    assert (path[0, [14, 15]] == -1).all()
    _, fixed = method.decode(lane, (motion + 2340)[None], fixed=True)
    assert np.count_nonzero(fixed[0] == 2) >= planted.sum() - 1


def test_background_and_no_training_leakage():
    t = np.arange(200, dtype=float) * 0.45
    y = np.zeros((len(t), method.PEAKS))
    marks = np.full_like(y, -np.inf)
    lane = method.Lane((0, 4, 11.4e9), np.arange(len(t)), t, y, marks)
    cost, path = method.decode(lane, np.array([t]))
    assert cost[0] == 0 and np.all(path[0] < 0)
    train, held = method.blocks(t)
    assert np.min(abs(t[train, None] - t[held])) >= 3.0


def test_elapsed_bridge_keeps_dense_native_cadence_across_six_missing_visits():
    t = np.arange(64, dtype=float) * 0.35
    predicted = 40000 + 980 * t + 72 * t * t
    y = np.zeros((len(t), method.PEAKS))
    y[:, 0] = method.fold(predicted - 1500)
    marks = np.full_like(y, -np.inf)
    marks[:, 0] = 1.3
    marks[28:34, 0] = -np.inf
    lane = method.Lane((1, 5, 12e9), np.arange(len(t)), t, y, marks)
    _, paths = method.decode(lane, predicted[None])
    expected = np.zeros(len(t), dtype=int)
    expected[28:34] = -1
    assert np.array_equal(paths[0], expected)


def test_selected_paths_are_disjoint_at_native_receiver_visit():
    lanes = [
        method.Lane((0, 3, 11.4e9), np.arange(3), np.arange(3), None, None),
        method.Lane((0, 2, 11.1e9), np.arange(3), np.arange(3), None, None),
    ]
    options = [
        dict(lane=0, orbit=10, phase=0.0, offset=1800.0, strength=5.0, visit=[1, 2]),
        dict(lane=1, orbit=20, phase=0.0, offset=1900.0, strength=4.0, visit=[1, 3]),
    ]
    selected, _ = method.choose(lanes, options)
    assert len(selected) == 1 and selected[0]["orbit"] == 10
