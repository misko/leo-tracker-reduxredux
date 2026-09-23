import numpy as np

from tools.research.plot_adaptive_retune_safe_phase import wrapped_visit_points


def test_retuned_visits_remain_independent_wrapped_points():
    states = [
        {"visit_index": 4, "time_s": 10.0, "phase_deg": 179.0},
        {"visit_index": 19, "time_s": 14.0, "phase_deg": -179.0},
    ]
    visits, time_s, phase_deg = wrapped_visit_points(states)
    assert visits.tolist() == [4, 19]
    assert time_s.tolist() == [0.0, 4.0]
    assert np.allclose(phase_deg, [179.0, -179.0])
    assert abs(np.diff(phase_deg)[0]) == 358.0
