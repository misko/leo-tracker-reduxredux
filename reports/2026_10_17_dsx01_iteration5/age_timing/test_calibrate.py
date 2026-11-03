import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('age_calibrate',
    Path(__file__).with_name('calibrate.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_causal_selection_deduplicates_and_never_reads_future():
    rows = [SimpleNamespace(collected_utc_ns=int(h*3600e9), digest=d)
            for h, d in ((0, 'old'), (1, 'same'), (2, 'same'), (4, 'new'), (5, 'future'))]
    result = module.select_snapshots(rows, int(5*3600e9))
    assert {s.digest for s in result} == {'same', 'new'}
    assert len(result) == 2  # Fixed lookbacks need not sample every older payload.
    assert all(s.collected_utc_ns < 5*3600e9 for s in result)


def test_projection_has_exact_units_and_orthogonal_remainder():
    dt, perpendicular, norm = module.decompose([14., 3., 4.], [0., 0., 0.], [7., 0., 0.])
    assert dt == 2 and perpendicular == 5 and norm == np.sqrt(221)
    with pytest.raises(ValueError):
        module.decompose([0, 0, 0], [0, 0, 0], [0, 0, 0])


def test_named_constellation_and_uniform_sampling_are_target_independent():
    cat = SimpleNamespace(names=('STARLINK-1', '0 STARLINK-2', 'OTHER'),
                          satellite_numbers=(9, 4, 1))
    assert module.starlink_indices(cat) == {9: 0, 4: 1}
    selected = module.uniform_numbers(range(2000), 1024)
    assert len(selected) == len(set(selected)) == 1024
    assert selected[0] == 0 and selected[-1] == 1999
