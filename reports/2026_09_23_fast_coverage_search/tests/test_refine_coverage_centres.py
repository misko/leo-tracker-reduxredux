import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools/research"))
from search_multiresolution_tle_coverage import (
    CellScore,
    ThresholdCoverage,
    refine_from_centres,
)

sys.path.pop(0)


def scorer(seen):
    def evaluate(points):
        result = []
        for e, n in points:
            key = (float(e), float(n))
            assert key not in seen
            seen.add(key)
            result.append(CellScore(*key, (
                ThresholdCoverage(200., 10, 1., 1, float(e * e + n * n), 1.),
            )))
        return result
    return evaluate


def test_seeded_refinement_uses_declared_lattice_without_duplicate_evaluations():
    seen = set()
    rows, trace = refine_from_centres(
        scorer(seen), np.asarray([[-25., -25.], [25., 25.]]),
        initial_spacing_km=50., radius_km=100., region_size_km=200.,
        levels_km=(25., 12.5), basins=4,
    )
    assert rows
    assert len(seen) == trace[-1]["cumulative_cell_count"]
    axis = set(((np.arange(16) + 0.5) / 16 - 0.5) * 200.)
    assert all(row.east_km in axis and row.north_km in axis for row in rows)
    assert all(np.hypot(row.east_km, row.north_km) <= 100. for row in rows)


def test_seed_on_final_lattice_is_retained_as_possible_winner():
    rows, _ = refine_from_centres(
        scorer(set()), np.asarray([[0., 0.]]), initial_spacing_km=200.,
        radius_km=400., region_size_km=1000., levels_km=(40.,), basins=8,
    )
    assert (rows[0].east_km, rows[0].north_km) == (0., 0.)


def test_seeded_refinement_rejects_coarsening():
    with pytest.raises(ValueError):
        refine_from_centres(
            scorer(set()), np.asarray([[0., 0.]]), initial_spacing_km=50.,
            radius_km=100., levels_km=(100.,),
        )
