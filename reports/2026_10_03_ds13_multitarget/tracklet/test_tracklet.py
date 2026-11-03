import numpy as np

from tracklet import Settings, generate_candidates, label_alternatives, select_exclusive


def synthetic(cross=False, miss=False, alias=False):
    t = np.repeat(np.arange(20.0), 2)
    rx = np.zeros(len(t), int)
    ch = np.ones(len(t), int)
    cats = np.array([10, 20])
    a = np.repeat(np.linspace(-200, 200, 20), 2)
    b = -a if cross else a + 800
    residual = np.column_stack((np.where(np.arange(len(t)) % 2 == 0, 0, 900),
                                np.where(np.arange(len(t)) % 2 == 1, 0, 900)))
    if cross:
        residual[18:22] = 30  # deliberately ambiguous at crossing
    if miss:
        residual[10:16, :] = 4000
    if alias:
        residual[::4, 1] = 1600
    return t, rx, ch, cats, residual


def test_simultaneous_paths_and_exclusivity():
    data = synthetic()
    paths = generate_candidates(*data, Settings(min_points=6, proposals_per_label_lane=1))
    chosen, result = select_exclusive(paths)
    assert result["success"]
    assert {p.catalog_number for p in chosen} == {10, 20}
    used = np.concatenate([p.rows for p in chosen])
    assert len(used) == len(np.unique(used))


def test_crossing_misses_alias_and_alternatives_are_finite():
    for kwargs in ({"cross": True}, {"miss": True}, {"alias": True}):
        data = synthetic(**kwargs)
        paths = generate_candidates(*data, Settings(min_points=5, proposals_per_label_lane=1))
        chosen, _ = select_exclusive(paths)
        assert chosen
        alternatives = label_alternatives(chosen[0], data[3], data[4])
        assert len(alternatives) == 2 and np.isfinite(alternatives[0][1])


def test_continuity_disabled_control_runs():
    data = synthetic(cross=True)
    settings = Settings(min_points=5, proposals_per_label_lane=1, continuity=False)
    chosen, result = select_exclusive(generate_candidates(*data, settings))
    assert result["success"] and chosen
