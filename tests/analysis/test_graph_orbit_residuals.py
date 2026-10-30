import copy
import numpy as np
import pytest
from audit_graph_orbit_residuals import original_polynomial


def test_piece_mapping_preserves_native_order_and_requires_exact_coverage():
    track=dict(indices=[9,3,7,1],times=[0,1,2,3],values=[10,11,21,20],pieces=[
        dict(indices=[3,9],reference_time_s=0,time_scale_s=1,coefficients_hz=[10]),
        dict(indices=[1,7],reference_time_s=0,time_scale_s=1,coefficients_hz=[20])])
    np.testing.assert_allclose(original_polynomial(track),[0,1,1,0])
    bad=copy.deepcopy(track);bad['pieces'][1]['indices']=[1,3]
    with pytest.raises(ValueError,match='overlap'):original_polynomial(bad)
    bad=copy.deepcopy(track);bad['pieces'][1]['indices']=[1]
    with pytest.raises(ValueError,match='cover'):original_polynomial(bad)
