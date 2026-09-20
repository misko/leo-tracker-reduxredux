from pathlib import Path

import numpy as np
import pytest


def test_blended_velocity_is_derivative_of_blended_position(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from replay_wide_alternative_tles import blend_states

    def at(t):
        t = np.asarray(t)
        p0 = np.column_stack([1 + 2 * t, t * 0, t * 0])
        p1 = np.column_stack([4 + 5 * t, t * 0, t * 0])
        return blend_states(
            p0, np.tile([2, 0, 0], (len(t), 1)), p1, np.tile([5, 0, 0], (len(t), 1)), t, 10
        )

    times = np.array([-2.0, 2.0, 5.0, 12.0])
    p, v = at(times)
    derivative = (at(times + 1e-4)[0] - at(times - 1e-4)[0]) / 2e-4
    np.testing.assert_allclose(v, derivative, atol=1e-8)
    assert p[0, 0] == -3
    assert p[-1, 0] == 64
    with pytest.raises(ValueError, match="positive epoch"):
        blend_states(p, v, p, v, times, 0)


def test_alternative_orbits_must_bind_same_order_and_identities(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from replay_wide_alternative_tles import validate_assignment_order

    rows = [dict(session_id="scan", episode_id=str(i), norad=i) for i in [1, 2]]
    validate_assignment_order(rows, [dict(r) for r in rows])
    for invalid in [list(reversed(rows)), rows[:1], [dict(rows[0], norad=3), rows[1]]]:
        with pytest.raises(ValueError, match="order or identity"):
            validate_assignment_order(rows, invalid)
