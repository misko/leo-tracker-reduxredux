"""A single-phase audit must preserve the original three physical orbit modes."""
from types import SimpleNamespace
import numpy as np

from audit_two_predictive_families import at_phases
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes


def test_single_phase_projection_replays_full_grid_physical_modes():
    knots = np.linspace(-20., 20., 81)
    times = np.array([-2., 0., 3.])
    phases = np.array([-.5, 0., .5])
    position = np.column_stack((7000.+knots, 1500.+7*knots, 2000.+2*knots))
    velocity = np.tile([1., 7., 2.], (len(knots), 1))
    bank = dict(time_s=knots, position_km=np.tile(position, (3, 1, 1)),
                velocity_km_s=np.tile(velocity, (3, 1, 1)))
    deviations = np.broadcast_to(np.eye(3)[:, None, :]*.01, (3, len(knots), 3)).copy()
    mode_bank = dict(time_s=knots, position_km=np.tile(deviations, (3, 1, 1)),
                     velocity_km_s=np.tile(deviations*.1, (3, 1, 1)))
    family = SimpleNamespace(times=times, phases=phases, bank=bank, modes=mode_bank)
    full = paired_frequency_modes(bank, mode_bank, np.tile(times, 3), np.repeat(np.arange(3), 3),
                                  phases, 37., -122.).reshape(3, 3, 3)
    for k, phase in enumerate(phases):
        f = at_phases([family], [phase])[0]
        single = paired_frequency_modes(f.bank, f.modes, f.grid_times, f.grid_labels, f.phases, 37., -122.)
        assert single.shape == (len(times), 3)
        np.testing.assert_allclose(single, full[k], atol=1e-12)
    assert family.bank['position_km'].shape[0] == 3
    assert family.modes['position_km'].shape[0] == 9
