from dataclasses import dataclass

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint


def test_fingerprints_cover_every_array_element_and_representation():
    value = np.arange(100., dtype=np.float64).reshape(10, 10)
    original = fingerprint(value)
    for changed in (value.astype(np.float32), value.reshape(100), value+1e-12):
        assert fingerprint(changed) != original
    assert fingerprint(value.copy()) == original
    assert fingerprint(-0.) != fingerprint(0.)


def test_nested_geometry_fields_are_not_omitted():
    @dataclass
    class Geometry:
        position: np.ndarray
        other: dict

    value = Geometry(np.ones((2, 3)), {'velocity': np.zeros((2, 3))})
    original = fingerprint(value)
    value.other['velocity'][1, 2] = 1e-12
    assert fingerprint(value) != original
    with pytest.raises(ValueError, match='Object arrays'):
        fingerprint(np.array([object()], dtype=object))
