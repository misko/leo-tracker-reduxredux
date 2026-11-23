import numpy as np

from leo.analysis.position_grid import sample_position_grid
from reports.ALGO08.v3.adaptive_grid_screen import choose_nodes, screen


def test_refines_either_calibration_and_outside_the_hull():
    initial = [(0, 0), (1, 0), (1, 1), (0, 1)]
    points = initial + [(.1, .1), (.9, .9), (1.1, .3)]
    scores = [[10, 10], [10, 10], [10, 0], [0, 10]]
    selected = choose_nodes(points, initial, scores)
    assert (.9, .9) in selected and (1.1, .3) in selected


def test_nonfinite_first_pass_refines_unresolved_triangles():
    initial = [(0, 0), (1, 0), (0, 1)]
    point = (.25, .25)
    assert point in choose_nodes([point], initial, [[np.nan, 0], [2, 8], [11, 4]])


def test_hidden_mode_outside_the_initial_refinement_is_counted():
    grid = sample_position_grid(lambda arm, p: p[0]**2+p[1]**2,
                                {"c0": (.1, .1), "fitted_c": (.2, .3)})
    first = screen(grid)
    chosen = set(first["selected_xy"])
    hidden = next(p for p in grid["points"] if (p["east_km"], p["north_km"]) not in chosen)
    hidden["scores"]["c0"] = -20.
    second = screen(grid)
    assert second["selected_xy"] == first["selected_xy"]
    assert second["arms"]["c0"]["missed_minima"] == 1
    assert not second["passed"]
