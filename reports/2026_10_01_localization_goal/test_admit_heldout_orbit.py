import numpy as np
import pytest
from admit_heldout_orbit import verify_extension


def fixture():
    extended = dict(satellite_ids=np.array([10, 20]), knot_times_s=np.arange(7.),
                    positions_ecef_km=np.arange(42.).reshape(2, 7, 3),
                    velocities_ecef_km_s=np.ones((2, 7, 3)))
    raw = {k: (v[:, 1:-1].copy() if v.ndim == 3 else
               v[1:-1].copy() if k == 'knot_times_s' else v.copy())
           for k, v in extended.items()}
    return raw, extended


def test_exact_original_knots_and_catalogue_are_required():
    raw, extended = fixture()
    verify_extension(raw, extended)
    extended['positions_ecef_km'][0, 2, 0] += .00001
    with pytest.raises(ValueError, match='physical states'):
        verify_extension(raw, extended)


def test_changed_identity_or_nonfinite_extension_is_rejected():
    raw, extended = fixture()
    extended['satellite_ids'][0] = 99
    with pytest.raises(ValueError, match='catalogue'):
        verify_extension(raw, extended)
    raw, extended = fixture()
    extended['velocities_ecef_km_s'][0, 0, 0] = np.nan
    with pytest.raises(ValueError, match='nonfinite'):
        verify_extension(raw, extended)
