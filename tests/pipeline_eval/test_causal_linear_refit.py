from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import history_policy as named
from reports.ALGO08.v3 import causal_linear_refit as warm
from reports.ALGO08.v3.causal_pre_refit_0155 import ENROLLED, SOURCE_PINS, compare_grid


def test_pre_refit_seed_uses_earlier_arm_state_and_original_satellite_labels():
    scan = SimpleNamespace(norads=[15,16,17], search_region=SimpleNamespace(half_width_km=12.5))
    node = dict(seed=dict(rows=[dict(candidate_index=2),dict(candidate_index=0)]))
    curved = {"c0":dict(endpoint_east_north_km=[1.,2.],state=dict(phases=[40.,100.,-2.])),
              "fitted_c":dict(endpoint_east_north_km=[-1.,2.],state=dict(phases=[-50.,200.,3.]))}
    ids, ref = warm.initial_states(scan, node, curved)
    assert ids == [0,2]
    assert tuple(vec.tolist() for vec in ref["c0"]) == ([1.,2.],[15.,-2.])
    assert tuple(vec.tolist() for vec in ref["fitted_c"]) == ([-1.,2.],[-15.,3.])


@pytest.mark.parametrize("accepted", [False, True])
def test_the_two_warm_outcomes_are_chosen_before_returning_either_arm(monkeypatch, accepted):
    scan, node, powers, means, model = (object() for _ in range(5))
    keep, entries = np.array([True,False]), [{"points":6}]
    trace, calls = [], []
    def original_linear(scan, node, keep, powers, means, model, arm, entries):
        calls.append(("cold",arm))
        return dict(endpoint_east_north_km=[0.,0.],negative_twice_elbo=1.,history=[{}], final_phase_change_s=0.)
    def trial(*args):
        calls.append(("warm","both"))
        return dict(c0="warm c0",fitted_c="warm fitted") if accepted else None
    monkeypatch.setattr(named,"history_fit",lambda *args,**kw: (None,keep,[]))
    monkeypatch.setattr(named,"linear_refit",original_linear)
    monkeypatch.setattr(warm,"try_warm",trial)
    with warm.linear_policy(True,trace):
        named.history_fit(scan,node,keep,powers,means,model)
        results = [named.linear_refit(scan,node,keep,powers,means,model,arm,entries) for arm in warm.ARMS]
    if accepted:
        assert results == ["warm c0","warm fitted"] and calls == [("warm","both")]
    else:
        assert calls == [("warm","both"),("cold","c0"),("cold","fitted_c")]
        assert set(trace[0]["cold_arms"]) == set(warm.ARMS)
    assert named.linear_refit is original_linear


def test_common_grid_comparison_never_interpolates_moved_point_scores():
    def grid(points):
        return dict(evaluated_points=len(points), points=[dict(east_km=e,north_km=0,scores=dict(c0=e*2,fitted_c=e*5)) for e in points])
    result = compare_grid(grid([1.,2.]),grid([1.,3.]))
    assert result["shared_coordinates"] == 1 and result["unique_coordinates"] == dict(control=1,warm=1)
    assert result["calibration"]["c0"]["changed_scores"] == 0


def test_history_retry_transfer_enrollment_preserves_exact_policy():
    transfer = ENROLLED["DS30-0160"]
    assert (transfer["windows"],transfer["admitted"],transfer["cutoff"]) == (3691,2354,1794782905318901898)
    assert transfer["stage"].is_relative_to("/dev/shm")
    assert SOURCE_PINS["causal_linear_refit.py"] == "a6b9e994845552bf3136a47f7b61a3df6badbd0a0509bbea5c021554dcfac905"
