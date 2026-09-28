import numpy as np
from boundary_tail_prediction import predicted_signs
from region_phase_audit import WORDS


def test_absolute_index_mapping_and_modulo_ambiguity():
    symbol = np.arange(2, 302)[:, None]
    carrier = np.arange(1004)[None]
    positions = (symbol - 2) * 1004 + carrier
    boundary = 63353
    expected = WORDS[(-boundary) % 60, (carrier - 16 * symbol) % 60]
    np.testing.assert_array_equal(predicted_signs(boundary, positions), expected)
    np.testing.assert_array_equal(predicted_signs(boundary + 60, positions), expected)
