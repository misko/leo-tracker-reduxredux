"""Epoch pairing preserves original scalar paths, support and normalization."""

from pathlib import Path

import pytest
from native_integer_screen import transform as integer_transform
from probe_integer_epoch_pair import transform


def integer_grid():
    root = Path(__file__).resolve().parents[2]/'src/leo/analysis/starlink'
    return integer_transform((root/'_native_acquisition.c').read_text(),
                             (root/'_native_acquisition_grid.inc').read_text())[1]


def test_original_scalar_epoch_loop_and_normalization_preserved():
    original = integer_grid()
    candidate = transform(original)
    begin = original.index('            for (npy_intp epoch = 0; epoch < valid_epochs; ++epoch) {')
    end = original.index('                support[epoch] += 1;', begin)
    end = original.index('\n            }', end)+len('\n            }')
    assert original[begin:end] in candidate
    normalization = original[original.index('                double received_energy ='):end]
    normalization = normalization[:normalization.rindex('\n            }')]
    assert candidate.count(normalization) == 2
    assert candidate.endswith(original[end:])


def test_odd_tail_cannot_read_or_accumulate_an_extra_epoch():
    candidate = transform(integer_grid())
    assert 'second = first+1 < valid_epochs ? first+1 : first;' in candidate
    assert 'lane < 2 && first+lane < valid_epochs' in candidate
    assert 'const npy_intp position = base+epoch;' in candidate


def test_unknown_native_layout_rejected():
    with pytest.raises(ValueError):
        transform('unknown')
