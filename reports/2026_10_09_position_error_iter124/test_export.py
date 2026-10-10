import runpy
from pathlib import Path

import pytest

api = runpy.run_path(str(Path(__file__).with_name("export.py")))


def test_signed_vector_summaries_and_alignment():
    result = api["summaries"]([[1, 2], [-1, 2]])
    assert result["mean_vector_km"] == [0, 2]
    assert result["coordinate_median_vector_km"] == [0, 2]
    assert result["rms_vector_km"] == pytest.approx(5**0.5)
    assert api["alignment"]([1, 0], [-2, 0]) == -1
    assert api["alignment"]([1, 0], [0, 1]) == 0
    assert api["alignment"]([0, 0], [1, 0]) is None
