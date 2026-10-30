import pytest
from test_predictive_graph_transfer import shared_family_route


def proposal(norad,kind):
    return dict(norad=norad,arms={a:dict(prior=dict(kind=kind)) for a in ('c0','fitted_c')})


def test_route_uses_winning_family_and_keeps_any_existing_calibration_shared():
    folds=[dict(proposals=[proposal(1,'new_family_causal_phase_mixture'),proposal(2,'existing_shared_posterior')])]
    assert not shared_family_route(folds,1)
    assert shared_family_route(folds,2)
    folds.append(dict(proposals=[proposal(1,'existing_shared_posterior')]))
    assert shared_family_route(folds,1)
    with pytest.raises(ValueError):shared_family_route(folds,3)
    with pytest.raises(ValueError):shared_family_route([dict(proposals=[proposal(1,'unknown')])],1)
