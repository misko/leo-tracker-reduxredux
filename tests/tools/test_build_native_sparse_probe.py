"""Sparse indexing must leave correlation and accumulation arithmetic unchanged."""

from pathlib import Path

import pytest
from build_native_sparse_probe import transform


def test_sparse_transform_preserves_arithmetic_and_original_entrypoints():
    root = Path(__file__).resolve().parents[2] / 'src/leo/analysis/starlink'
    source, grid = [(root / n).read_text() for n in
                    ('_native_acquisition.c', '_native_acquisition_grid.inc')]
    changed, sparse = transform(source, grid)
    marker = '#if defined(LEO_GRID_CORRELATE)'
    assert grid.split(marker)[1] == sparse.split(marker)[1]
    assert 'epoch_indices[i] >= epoch_count' in changed
    assert changed.count(', NULL, 0);') == 4
    assert 'PyArray_TYPE((PyArrayObject *)object) != NPY_INTP' in changed
    assert 'selected_epoch >= valid_position_count - base' in sparse
    assert 'const npy_intp *epoch_indices;' in changed


@pytest.mark.parametrize('source,grid', [('', ''), ('different', 'different')])
def test_unknown_source_rejected(source, grid):
    with pytest.raises(ValueError):
        transform(source, grid)
