import numpy as np
from plot_independent_offsets import ALIAS_HZ, align_alias


def test_alias_alignment_preserves_offset_modulo_native_period():
    offsets = np.array([-132064.539197, 98000, 91000 + 3 * ALIAS_HZ])
    aligned = align_alias(offsets)
    np.testing.assert_allclose(align_alias(offsets + 4 * ALIAS_HZ), aligned)
    shifts = (aligned - offsets) / ALIAS_HZ
    np.testing.assert_allclose(shifts, np.rint(shifts), atol=1e-12)
