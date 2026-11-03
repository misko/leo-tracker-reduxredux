"""The approximate experiment is limited to correlation, retaining FP64 normalization."""

from pathlib import Path

import pytest
from build_native_screen_probe import transform

ROOT = Path(__file__).resolve().parents[2] / 'src/leo/analysis/starlink'


def sources():
    return [(ROOT / name).read_text() for name in
            ('_native_acquisition.c', '_native_acquisition_grid.inc')]


def test_fp32_screen_preserves_normalization_and_nonregister_arithmetic():
    source, grid = sources()
    changed_source, changed_grid = transform(source, grid)
    assert changed_source.replace('cfo_count == 24', 'cfo_count == 12').replace(
        '#include <stdlib.h>\n', '') == source
    original_tail = grid.split('                double received_energy =', 1)[1]
    changed_tail = changed_grid.split('                double received_energy =', 1)[1]
    assert original_tail.split('    kernel->invalid_geometry')[0] == changed_tail.split(
        '#if defined(LEO_GRID_AVX2_12_REGISTER_ACCUMULATION)')[0]
    assert '_mm256_fmadd_ps' in changed_grid and '_mm256_fnmadd_ps' in changed_grid
    assert 'index * 24' in changed_grid
    assert 'correlation_real[f] = real32[f]' in changed_grid
    assert 'reference_energy +=' in changed_grid


@pytest.mark.parametrize('which', [0, 1])
def test_unknown_layout_rejected(which):
    args = sources()
    args[which] = ''
    with pytest.raises(ValueError):
        transform(*args)
