from reports.ALGO08.v3.ds30_0359_predictive_score import image_identity, scaled_clocks


def test_same_factor_clock_charges_common_measurement_to_each_estimate():
    trace = {f"{name}_{metric}_ns": scale for metric in ("cpu", "wall") for name, scale in
             (("stock_predictive", 1_500_000_000), ("candidate_predictive", 1_200_000_000), ("paired_grid", 5_000_000_000))}
    costs = scaled_clocks(trace)
    assert costs["cpu"]["common_grid_and_observer_s"] == 2.3
    assert costs["cpu"]["estimated_stock_grid_s"] == 3.8
    assert costs["cpu"]["estimated_reduced_grid_s"] == 3.5


def test_exact_image_contract_distinguishes_pixels_from_encoded_bytes():
    archived = dict(position=dict(sha256="compressed", rgba_sha256="pixels", size=[1, 2]))
    candidate = dict(position=dict(archived["position"], size=(1, 2)))
    assert image_identity(archived, candidate) == {"position": True}
    candidate["position"]["sha256"] = "changed compression"
    assert image_identity(archived, candidate) == {"position": False}
