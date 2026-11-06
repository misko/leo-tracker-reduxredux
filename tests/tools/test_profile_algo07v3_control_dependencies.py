import os

import numpy as np
import pytest
from profile_algo07v3_control_dependencies import array_buffer, observed_compute

from leo.analysis.localization_v3.scan import ScanLikelihood


@pytest.mark.parametrize('value', [
    np.arange(12).reshape(3, 4), np.arange(12).reshape(3, 4).T,
    np.arange(10)[::-2], np.array(3.), np.empty((0, 4)),
    np.array(['abc', 'def']), np.array([1., -0., np.nan]),
])
def test_buffer_hash_matches_original_bytes(value):
    import hashlib
    assert hashlib.sha256(array_buffer(value)).digest() == hashlib.sha256(
        value.tobytes(order='C')).digest()


def test_observer_records_child_and_restores_class(tmp_path):
    scan = object.__new__(ScanLikelihood)
    scan.center = [1, 2]
    original = ScanLikelihood.__getattribute__

    def compute():
        child = os.fork()
        if not child:
            assert scan.center == [1, 2]
            os._exit(0)
        assert os.waitpid(child, 0)[1] == 0
        return scan.center

    path = tmp_path / 'trace.jsonl'
    assert observed_compute(compute, path) == [1, 2]
    assert ScanLikelihood.__getattribute__ is original
    assert path.read_text().count('"attribute": "center"') == 2
    with pytest.raises(ValueError):
        observed_compute(lambda: (_ for _ in ()).throw(ValueError('failed')),
                         tmp_path / 'failed.jsonl')
    assert ScanLikelihood.__getattribute__ is original
