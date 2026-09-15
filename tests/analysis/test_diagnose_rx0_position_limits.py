import gzip
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).parents[2] / "tools" / "diagnose_rx0_position_limits.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("diagnose_rx0_position_limits", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_fitted_centre_uses_training_offset_only():
    values = np.array([1.0, 3.0, 100.0])
    answer = module.fitted_centre(values, np.array([True, True, False]))
    np.testing.assert_allclose(answer, [-1.0, 1.0, 98.0])


def test_quadrant_counts_wraps_north():
    answer = module.quadrant_counts(np.array([350.0, 10.0, 90.0, 180.0, 270.0]))
    assert answer == {"N": 2, "E": 1, "S": 1, "W": 1}


def test_haversine_known_degree_scale():
    np.testing.assert_allclose(module.haversine_km((0.0, 0.0), (1.0, 0.0)), 111.195, atol=0.001)


def test_track_sampling_summary_reads_published_review(tmp_path):
    document = {
        "screen": {
            "tracks": [
                {
                    "time_s": [0.0, 1.0, 3.0],
                    "span_s": 3.0,
                    "observations": 3,
                }
            ]
        }
    }
    (tmp_path / "scan-hop-test.json.gz").write_bytes(gzip.compress(json.dumps(document).encode()))
    answer = module.track_sampling_summary(tmp_path)
    assert answer["recording_count"] == 1
    assert answer["track_count"] == 1
    assert answer["median_observation_interval_s"] == 1.5
