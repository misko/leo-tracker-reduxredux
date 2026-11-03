"""Position decoding diagnostic, independent of any target reference."""

import numpy as np
from state_diagnostics import distance_km


def test_configured_distance_identical_and_known_great_circle():
    reference = dict(latitude_deg=0.0, longitude_deg=0.0)
    assert distance_km(0.0, 0.0, reference) == 0
    assert np.isclose(distance_km(0.0, 1.0, reference), 6371.0088 * np.pi / 180)
