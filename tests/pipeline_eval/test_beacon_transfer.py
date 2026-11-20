import numpy as np

from tools.pipeline_eval.variants import beacon_transfer as model


def edge(norad, value):
    return dict(norad=norad, wrapped_level_hz=value)


def test_single_cross_site_repeat_connects_graph_without_closure_check():
    result = model.graph(
        {
            "capture1": [edge(1, 500), edge(2, 800)],
            "capture2": [edge(2, 2400), edge(3, 300)],
            "capture3": [edge(4, -7000)],
        }
    )
    assert len(result) == 2
    a, b = result
    assert a["cycle_rank"] == b["cycle_rank"] == 0
    np.testing.assert_allclose(a["captures"]["capture2"], 1600)
    np.testing.assert_allclose(a["levels"]["3"], -1300)
    np.testing.assert_allclose(b["levels"]["4"], -7000)


def test_singleton_level_and_harmonic_are_absorbed_by_one_target_clock():
    x = np.array([19000, 19500, 18500.0])
    y = np.array([19020, 19540, 18300.0]) + model.COMB
    _, e = model.common_clock([(x, y)], [600])
    _, null = model.common_clock([(x, y)], [22000])
    np.testing.assert_allclose(e, null, atol=1e-9)
    np.testing.assert_allclose(e[0, 1], e[0, 2], atol=1e-9)


def test_two_level_differences_survive_common_receiver_clock():
    a = (np.array([1200.0, 1200]), np.array([1200.0, 1200]))
    b = (np.array([4500.0, 4500]), np.array([4500.0, 4500]))
    clock, good = model.common_clock([a, b], [200, 3500])
    _, swapped = model.common_clock([a, b], [3500, 200])
    np.testing.assert_allclose(clock, 1000, atol=1e-9)
    np.testing.assert_allclose(good, 0, atol=1e-9)
    assert np.min(swapped[:, 1]) > 1000


def test_donors_exclude_target_site_and_noncausal_capture_end():
    q = dict(site="b", start_utc_ns=100)
    rows = [
        dict(site="a", end_utc_ns=99),
        dict(site="a", end_utc_ns=110),
        dict(site="b", end_utc_ns=33),
        dict(site="b", end_utc_ns=139),
    ]
    assert model.partition(rows, q) == [rows[0]]
    assert model.partition(rows, q, strict=False) == rows[:2]
