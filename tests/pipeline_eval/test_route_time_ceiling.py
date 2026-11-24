from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from route_time_ceiling import evaluate, receipt


def test_distinct_routes_charge_their_own_measured_elapsed_intervals():
    mixed = receipt("live-stereo-north.json.gz")
    live = receipt("eight-ms-native-live.json.gz")
    budget = evaluate(mixed, live)
    assert budget["masked_fallback_free"]["seconds_above_half"] == pytest.approx(1.48542, abs=1e-4)
    assert budget["all8_short_free"]["seconds_above_half"] == pytest.approx(.59014, abs=1e-4)
    assert budget["masked_fixed_error_m"] > budget["all8_fixed_error_m"] + 700
    live["scientific_seal"]["historical"]["named"]["exit_code"] = 1
    with pytest.raises(ValueError, match="successful"):
        evaluate(mixed, live)
