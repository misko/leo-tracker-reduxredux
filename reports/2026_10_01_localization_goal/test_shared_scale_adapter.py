import numpy as np
from shared_scale_adapter import make_groups
from test_nonlinear_gaussian_adapter import Port


def test_grouping_preserves_every_observation_and_background():
    ports = [Port() for _ in range(3)]
    for i, p in enumerate(ports):
        p.observation_ids = (f'{i}a', f'{i}b')
    grouped, members = make_groups(ports, np.zeros(7), [0, 0, 2], 'satellite')
    assert members == [[0, 1]] and len(grouped) == 2
    assert grouped[-1].score_selected(np.zeros(7), 0) == -7.
    singleton, separate = make_groups(ports, np.zeros(7), [0, 0, 2], 'singleton')
    assert separate == [[0], [1]] and len(singleton) == 3
    assert sorted(i for p in grouped for i in p.observation_ids) == sorted(
        i for p in singleton for i in p.observation_ids)
