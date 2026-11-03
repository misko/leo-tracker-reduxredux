from evaluate_truth_start import local_descent_verified


def test_local_descent_requires_gradient_agreement_and_small_downhill_step():
    audit = {"gradient_per_km": [2., -3.],
             "central_difference_gradient_per_km": [2., -3.],
             "fixed_nuisance_downhill_steps": [{"step_m": .1, "loss_change": -.001}]}
    assert local_descent_verified(audit)
    audit["central_difference_gradient_per_km"] = [-2., 3.]
    assert not local_descent_verified(audit)
    audit["central_difference_gradient_per_km"] = [2., -3.]
    audit["fixed_nuisance_downhill_steps"][0]["loss_change"] = .001
    assert not local_descent_verified(audit)
