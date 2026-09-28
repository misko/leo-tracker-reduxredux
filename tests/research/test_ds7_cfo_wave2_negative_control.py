import numpy as np

from tools.ds7_cfo_wave2_negative_control import symbol_phase_scramble


def test_symbol_scramble_is_deterministic_and_not_static_tone_gain() -> None:
    original = np.ones((150, 8), dtype=np.complex128)
    first = symbol_phase_scramble(original, seed=41, candidate_id="candidate", frame_index=2)
    second = symbol_phase_scramble(original, seed=41, candidate_id="candidate", frame_index=2)

    np.testing.assert_array_equal(first, second)
    np.testing.assert_allclose(np.abs(first), np.abs(original))
    # A static nuisance gain per tone would make each column constant in time.
    assert all(len(np.unique(first[:, tone])) > 1 for tone in range(first.shape[1]))
    # The identical phase across tones preserves instantaneous tone relationships.
    np.testing.assert_array_equal(first[:, 0], first[:, -1])
