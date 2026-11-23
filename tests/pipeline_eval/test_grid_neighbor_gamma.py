"""The sampled geometry and precision screen stay fixed across convergence modes."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_neighbor_gamma import MODES, prepared_source, score_rows, sweep_points


def test_fixed_sweeps_select_only_given_coordinates():
    expected = [(-1.5, .5), (-1., .5), (-.5, .5), (0., .5), (0., 0.), (3.125, 0.), (6.25, 0.), (9.375, 0.),
                (-12.5, -12.5), (-9.375, -12.5), (-6.25, -12.5), (-3.125, -12.5)]
    points = [dict(east_km=x, north_km=y) for x, y in expected]
    assert [point for sweep in sweep_points({"points": points}, [0., 0.]).values() for point in sweep] == points
    with pytest.raises(KeyError):
        sweep_points({"points": points[:-1]}, [0., 0.])


def test_precision_screen_records_direction_and_rejects_excess_score_drift():
    rows = []
    for arm in ("c0", "fitted_c"):
        for index in range(12):
            values = {mode: dict(score=float(index), status=0, export=1, seeded=index % 4 != 0,
                                 final_change=1e-10, updates=12, kernel_cpu_ns=1200) for mode in MODES}
            values["warm"]["score"] -= 2e-5 if index == 5 else 0.
            rows.append(dict(arm=arm, archived_score=float(index), observations=values))
    report = score_rows(rows)
    for arm in report.values():
        assert arm["archived_stock_exact"] and arm["all_checked"] and arm["converged"]
        assert arm["score_delta"]["stock"]["min"] == pytest.approx(-2e-5)
        assert arm["score_delta"]["stock"]["over_limit"] == 1
        assert arm["warm_seeds"] == 9


def test_mismatched_native_export_source_is_rejected():
    with pytest.raises(ValueError, match="pinned posterior exporter"):
        prepared_source("int some_other_kernel(void);")
