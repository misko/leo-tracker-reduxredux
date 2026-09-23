import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tools/research"))
import run_best_first_tle_search as runner
from best_first_tle_search import TrackResidual, point_evaluation

sys.path.pop(0)


@pytest.mark.parametrize("setting,value", [
    ("radius_km", 501.), ("radius_km", 0.), ("workers", 0), ("workers", 13),
    ("budget_points", 99), ("cities", []), ("cities", ["denver"]),
    ("cities", ["sacramento", "sacramento"]),
])
def test_invalid_programmatic_search_rejected_before_io(tmp_path, setting, value):
    args = SimpleNamespace(radius_km=500., workers=12, budget_points=400,
                           cities=["sacramento"], output=tmp_path / "new")
    setattr(args, setting, value)
    with pytest.raises(ValueError):
        runner.run(args)
    assert not args.output.exists()


@pytest.mark.parametrize("spacing,count", [(12.5, 64), (25., 16), (6.25, 256)])
def test_local_reference_stays_within_selected_coarse_cell(spacing, count):
    points = runner.exact_descendants(-150., 50., spacing)
    assert len(points) == count
    assert len({tuple(point) for point in points}) == count
    assert np.all(np.abs(points[:, 0] + 150.) < 50.)
    assert np.all(np.abs(points[:, 1] - 50.) < 50.)


def test_uncapped_diagnostic_does_not_hide_cap_or_unmatched_track():
    row = point_evaluation(0., 0., [
        TrackResidual("large", 1000., 1.), TrackResidual("small", 0., 3.),
        TrackResidual("missing", None, 2.),
    ])
    diagnostic = runner.residual_diagnostics(row)
    assert diagnostic["uncapped_matched_track_weighted_rms_hz"] == 500.
    assert diagnostic["unmatched_track_count"] == 1
    assert diagnostic["matched_track_count"] == 2
    assert row.weighted_mse_hz2 == 320000.
