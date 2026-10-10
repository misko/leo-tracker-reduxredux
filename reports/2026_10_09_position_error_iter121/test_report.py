import runpy
from pathlib import Path

import pytest

api = runpy.run_path(str(Path(__file__).with_name('report.py')))


def test_error_convention_and_statistics():
    assert api['error']([38,-121],[38,-121]) == 0
    assert api['error']([0,0],[0,1]) == pytest.approx(111.1950802335329)
    result = api['metrics']([1,2,3])
    assert result['count'] == 3
    assert result['mean_km'] == result['median_km'] == 2
    assert result['worst_km'] == 3
