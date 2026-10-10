import copy
import json
import runpy
from pathlib import Path

api = runpy.run_path(str(Path(__file__).with_name("reconstruct.py")))


def test_reference_perturbations_do_not_change_inference_projection():
    document = {
        "session_id": "id",
        "input_manifest_sha256": "input",
        "analysis_manifest_sha256": "analysis",
        "methods": [
            {
                "arms": [
                    {
                        "name": "fitted-c",
                        "selected": {
                            "source_basin": "b",
                            "satellites": [1, 2],
                            "horizontal_error_m": 123,
                        },
                    }
                ]
            }
        ],
        "diagnostics": {
            "calibrations": {
                "b": {
                    "receiver_baseline_hz": [1, 2],
                    "correction": {"nodes_s": [0, 1], "knots_hz": [[1, 2], [3, 4]]},
                }
            }
        },
        "reference_latitude_deg": 38,
        "reference_longitude_deg": -121,
    }
    expected = api["regional_document"](document)
    changed = copy.deepcopy(document)
    changed["reference_latitude_deg"] = 0
    changed["methods"][0]["arms"][0]["selected"]["horizontal_error_m"] = 999999
    assert api["regional_document"](changed) == expected
    del changed["reference_latitude_deg"]
    del changed["reference_longitude_deg"]
    del changed["methods"][0]["arms"][0]["selected"]["horizontal_error_m"]
    assert api["regional_document"](changed) == expected
    assert "reference" not in json.dumps(expected) and "error" not in json.dumps(expected)
