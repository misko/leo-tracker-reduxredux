import numpy as np
from overlay import restore_prediction


def test_radio_offset_restoration_and_witness_redaction():
    y=np.array([100.,120.]);parent=np.array([4.,5.]);raw=y-parent;prediction=np.array([60.,80.])
    assert np.array_equal(restore_prediction(y,raw,prediction),prediction+parent)
    delta=np.array([50.,-70.])
    assert np.array_equal(restore_prediction(y+delta,raw+delta,prediction),prediction+parent)
