import pytest
from bandwidth_receipt_audit import disagreement


def test_disagreement_weights_decisions_not_frame_averages():
    rows = [dict(errors=[1], count=[1]), dict(errors=[0], count=[9])]
    assert disagreement(rows, [0]) == .1
    with pytest.raises(ValueError, match="No decisions"):
        disagreement([dict(errors=[0], count=[0])], [0])
