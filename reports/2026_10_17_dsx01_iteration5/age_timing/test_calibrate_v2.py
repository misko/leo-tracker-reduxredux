import importlib.util
from pathlib import Path

import numpy as np

from leo.sky.sampling import SamplingGrid

spec = importlib.util.spec_from_file_location('age_calibrate_v2',
    Path(__file__).with_name('calibrate_v2.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_public_grid_contract_and_exact_causal_reference():
    times = module.propagation_times()
    assert len(times) == 3 and times[-1] == 0 and np.all(np.diff(times) > 0)
    anchor = 1792166536105889082
    epochs = tuple(anchor+round(float(t)*1e9) for t in times)
    grid = SamplingGrid(epochs, 0, 1.)
    assert grid.utc_ns[-1] == anchor and max(grid.utc_ns) == anchor


def test_projection_is_unchanged_at_final_reference_epoch():
    positions = np.array([[[[999., 0., 0.], [888., 0., 0.], [14., 3., 4.]]]])
    dt, perpendicular, norm = module.decompose(positions[0, 0, -1], [0., 0., 0.], [7., 0., 0.])
    assert dt == 2 and perpendicular == 5 and norm == np.sqrt(221)
