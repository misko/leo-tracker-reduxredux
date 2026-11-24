import sys
from math import inf, nextafter
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from signed_phase_identifiability import bound_arms, checkpoint, refresh_history, sampled_geometry


def test_signed_grid_profiles_the_displacement_on_one_surface():
    points = [dict(east_km=x, north_km=y, scores={"c0": 30 + 2*x*x + x*y + 3*y*y})
              for x in range(-2, 3) for y in range(-2, 3)]
    grid = dict(complete=True, endpoints={"c0": [0, 0]}, points=points, local_size=5, local_half_width_km=2)
    start = {"east_north_km": [1, 1], "objective": -100}
    end = {"east_north_km": [0, 0], "objective": 30}
    geometry = sampled_geometry(grid, start, end, "c0")
    assert geometry["hessian_score_per_km2"] == [[4, 1], [1, 6]]
    assert geometry["quadratic_score_delta"] == geometry["bilinear_score_delta"] == 6
    assert sampled_geometry(grid, start, dict(end, objective=31), "c0") is None
    assert sampled_geometry(dict(grid, local_size=1), start, end, "c0") is None


def test_boundary_readout_preserves_the_installed_binary64_face_rule():
    before = dict(c0={"east_north_km": [nextafter(12.5, -inf), 0]}, fitted_c={"east_north_km": [0, 0]})
    assert bound_arms(before, 25) == ["c0"]
    assert bound_arms(dict(before, c0={"east_north_km": [12.51, 0]}), 25) is None


def test_signed_comparison_uses_repaired_pair_and_rejects_support_changes():
    def record(e, points=5):
        return dict(latlon=[1., 2.], east_north_km=[e, 0.], objective=3., rf_rms_hz=10.,
                    curved_points=points, linear_points=0, failed_curved=[], failed_linear=[], final_phase_change_s=.01)

    original = dict(c0=record(3), fitted_c=record(4))
    repaired = dict(c0=record(1), fitted_c=record(2))
    accepted = dict(c0=record(1.5), fitted_c=record(2.5))
    trial = dict(finish=original, repair=dict(status="complete", finish=repaired),
                 signed=dict(status="accepted", finish=accepted))
    result = checkpoint(trial)
    assert result["origin"] == "accepted repair"
    assert result["comparison"]["c0"]["move_km"] == .5
    trial["signed"]["finish"]["fitted_c"] = record(2.5, 4)
    assert checkpoint(trial)["comparison"] is None


def test_repeated_position_does_not_imply_phase_is_unchanged():
    history = [dict(position=[1, 0], evaluations=7, phase_change_s=3.),
               dict(position=[2, 0], evaluations=5, phase_change_s=.4),
               dict(position=[2, 0], evaluations=3, phase_change_s=.001),
               dict(position=[2, 0], evaluations=3, phase_change_s=.00001)]
    audit = refresh_history(history)
    assert audit["terminal_position_first_round"] == 2
    assert audit["objective_calls"] == 18
    assert audit["side_calls_at_unchanged_endpoint"] == 4
    assert audit["late_phase_unchanged"] is False
