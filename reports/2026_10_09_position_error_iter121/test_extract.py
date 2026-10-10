import runpy
from pathlib import Path


def test_prior_transform_ignores_truth_and_exports_only_position_fields():
    api = runpy.run_path(str(Path(__file__).with_name("extract.py")))
    prior = {"latitude_deg": 38.0, "longitude_deg": -121.0, "altitude_m": 0.0, "radius_km": 250.0}
    operation = {
        "fit": {
            "vector": [0.0, 0.0],
            "converged": True,
            "stop_reason": "qualified",
            "reference_latitude_deg": 90,
            "error_km": 1000,
        }
    }
    result = api["position_only"](operation, prior)
    assert result["latlon"] == [38.0, -121.0]
    assert set(result) == {"latlon", "qualified", "qualification_reason", "selection"}
    assert api["position_only"](None, prior) is None
