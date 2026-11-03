import hashlib
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from export_recorded_scan_iq import raw_visit


def test_both_receivers_and_entire_dwell_preserved():
    values = np.zeros((300000,2,2), dtype='<i2')
    values[0] = [[-32768,32767],[123,-456]]
    values[-1] = [[42,-42],[987,-789]]
    raw, digest = raw_visit(values)
    assert len(raw) == 2400000
    assert digest == hashlib.sha256(raw).hexdigest()
    assert np.array_equal(np.frombuffer(raw,dtype='<i2').reshape(values.shape),values)


@pytest.mark.parametrize('values', [
    np.zeros((50000,2,2),dtype='<i2'),
    np.zeros((300000,2,2),dtype='>i2'),
    np.zeros((300000,2,2),dtype='<f4'),
    np.zeros((300000,2,2),dtype='<i2')[:,::-1,:],
])
def test_rejects_partial_reordered_or_retyped_iq(values):
    with pytest.raises(ValueError):raw_visit(values)
