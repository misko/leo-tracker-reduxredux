import numpy as np
import pytest
from report import block_rows


def test_blocks_preserve_pairing_and_debit_losses():
    rows = block_rows(np.array([5., 21., 22., 61.]), np.array([False, True, True, True]),
        np.array([99., 5., 6., 7.]), np.array([0., 4., 8., 5.]),
        np.array([True, True, False, True]), np.array([False, False, True, True]))
    assert len(rows)==2 and sum(r['observations'] for r in rows)==3
    assert rows[0]['new']==1 and rows[0]['lost']==1
    assert rows[0]['nll_delta']==1. and rows[1]['nll_delta']==-2.
    assert sum(r['nll_delta'] for r in rows)==-1.


def test_misaligned_arrays_and_nonboolean_masks_rejected():
    with pytest.raises(ValueError):
        block_rows([1], [True, False], [1], [2], [True], [True])
    with pytest.raises(ValueError):
        block_rows([1], [1], [1], [2], [True], [True])
