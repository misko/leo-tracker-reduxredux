import numpy as np
import pytest
from scaled_optimizer_trial import Scaled


def test_scaling_preserves_loss_gradient_relation_and_metadata():
    class Objective:
        scale=np.ones(2)
        def evaluate(self,x):return float(np.dot(x,x)),2*x
    original=Objective();scaled=Scaled(original,20)
    v=np.array([2.,3.]);f,g=scaled.evaluate(v)
    assert f==13/20
    np.testing.assert_allclose(g,[.2,.3])
    assert scaled.scale is original.scale
    with pytest.raises(ValueError):Scaled(original,0)
