import numpy as np
import pytest
from validate_shared_family_blocks import held_prediction


def test_held_values_cannot_change_training_bias():
    raw=np.arange(8.)*7;train=np.arange(8)<4;held=~train
    first=held_prediction(raw,train,held)
    changed=raw.copy();changed[held]+=10000
    second=held_prediction(changed,train,held)
    assert first['training_bias_hz']==second['training_bias_hz']
    assert first['training_bias_hz']==pytest.approx(raw[train].sum()/4.5)
    np.testing.assert_allclose(second['held_residual_hz']-first['held_residual_hz'],10000)


def test_overlapping_partition_is_rejected():
    with pytest.raises(ValueError,match='disjoint'):
        held_prediction(np.arange(8.),np.ones(8,bool),np.ones(8,bool))
