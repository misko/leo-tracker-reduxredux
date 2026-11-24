from reports.ALGO08.v3.history_risk_cairo_0402 import failed_layers


def test_registered_orbit_layers_require_both_directions():
    panels = {"orbit": {"rows": [
        {"gray": {"fraction": [.99, .979]}, "color": {"fraction": None}},
        {"gray": {"fraction": [.98, .99]}, "color": {"fraction": [.91, .99]}},
    ]}}
    assert failed_layers(panels) == [
        {"sheet": "orbit", "panel": 1, "layer": "gray", "fraction": [.99, .979]},
        {"sheet": "orbit", "panel": 2, "layer": "color", "fraction": [.91, .99]},
    ]
