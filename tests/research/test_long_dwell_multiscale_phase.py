import numpy as np

from tools.research.replay_long_dwell_multiscale_phase import carrier_phase, wrap


def test_affine_carrier_transport_is_translation_invariant():
    model = (2.0, -3500.0, 180000.0)
    center = 4.25
    for origin in (0.0, 3.9):
        local_removed = carrier_phase(model, center) - carrier_phase(model, origin)
        restored = local_removed + carrier_phase(model, origin)
        assert abs(wrap(restored - carrier_phase(model, center))) < 1e-9


def test_double_difference_has_ordinary_two_pi_gauge():
    assert np.isclose(abs(wrap(np.pi)), np.pi)
