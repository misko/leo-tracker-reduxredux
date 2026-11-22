from importlib import import_module

from matplotlib import pyplot as plt

render = import_module("reports.ALGO08.single-core-2x.publication_render_profile")


def test_skip_only_repeated_empty_residuals_within_one_axis():
    fig, (a, b) = plt.subplots(1, 2)
    try:
        with render.residual_scatter(skip=True) as counts:
            assert a.scatter([], [], s=5, c="blue") is not None
            assert a.scatter([], [], s=5, c="green") is None
            assert b.scatter([], [], s=5, c="blue") is not None
            assert a.scatter([], [], s=6, c="green") is not None
            assert b.scatter([2], [3], s=5, c="blue") is not None
        assert counts == {"empty": 3, "omitted": 1, "other": 2}
    finally:
        plt.close(fig)
