import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).parents[2] / "reports/2026_09_23_long_training_duration_ablation/run.py"
SPEC = importlib.util.spec_from_file_location("duration_ablation", PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_restrict_preserves_input_masks_and_filters_only_by_span():
    short = {
        "times_s": np.array([0.0, 9.0]),
        "training_mask": np.array([True, False]),
        "weight_s": 1,
    }
    long = {
        "times_s": np.array([0.0, 10.0]),
        "training_mask": np.array([False, True]),
        "weight_s": 3,
    }
    original = [{"prepared": [short, long], "weight": 4, "session_id": "s"}]
    restricted = module.restrict(original, 10)
    assert restricted[0]["prepared"] == [long]
    assert restricted[0]["weight"] == 3
    assert original[0]["prepared"][0] is short
    assert original[0]["prepared"][1] is long
    assert np.array_equal(long["training_mask"], np.array([False, True]))


def test_held_summary_uses_evaluation_rms_and_preserves_unmatched_penalty():
    class Base:
        @staticmethod
        def combined_score(*_args):
            return 1.0, [{"tracks": [{"evaluation_rms_hz": 20.0}, {}]}]

    sessions = [{"prepared": [{"weight_s": 1}, {"weight_s": 3}]}]
    result = module.held_summary(
        Base(), object(), sessions, {"latitude_deg": 0, "longitude_deg": 0}
    )
    assert result["capped800_rmse_hz"] == np.sqrt((20.0**2 + 3 * 800.0**2) / 4)
