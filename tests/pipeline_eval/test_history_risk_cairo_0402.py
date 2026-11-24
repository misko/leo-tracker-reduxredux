from reports.ALGO08.v3.history_risk_cairo_0402 import TIMED_DRIVER, failed_layers, renderer_witness, source_digest


def test_registered_orbit_layers_require_both_directions():
    panels = {"orbit": {"rows": [
        {"gray": {"fraction": [.99, .979]}, "color": {"fraction": None}},
        {"gray": {"fraction": [.98, .99]}, "color": {"fraction": [.91, .99]}},
    ]}}
    assert failed_layers(panels) == [
        {"sheet": "orbit", "panel": 1, "layer": "gray", "fraction": [.99, .979]},
        {"sheet": "orbit", "panel": 2, "layer": "color", "fraction": [.91, .99]},
    ]


def test_rescoring_permits_only_the_timed_driver_change():
    driver = "history_risk_cairo_0402.py"
    current = {driver: "reducer fix", "drawing.py": "original"}
    paid = current | {driver: TIMED_DRIVER}
    binding = {"sources": paid, "sha256": source_digest(paid)}
    assert renderer_witness(binding, paid, current)
    assert not renderer_witness(binding, current, current)
    changed = paid | {"drawing.py": "updated"}
    assert not renderer_witness({"sources": changed, "sha256": source_digest(changed)}, changed, current)
