import importlib.util
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("likelihood_diagnostics",HERE/"diagnostics.py")
assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(module)


def test_normalized_log_weights_extreme_and_normalized():
    result=module.normalized_log_weights(np.array([-10000.,-10001.,-20000.]))
    assert np.isclose(result.sum(),1.) and np.all(np.isfinite(result))
    assert result[0] > result[1] > result[2]


def test_roof_offset_is_far_from_sacramento_and_deterministic():
    first=module.en_from_geodetic(37.849056280893684,-122.48575489722863,38.5816,-121.4944)
    second=module.en_from_geodetic(37.849056280893684,-122.48575489722863,38.5816,-121.4944)
    assert first == second
    assert 100 < np.hypot(*first) < 150


def test_same_callback_check_is_not_presented_as_independent_validation():
    source=(HERE/"diagnostics.py").read_text()
    assert '"independent_forward_model": False' in source
    assert '"kind": "same_callback_wiring_check"' in source
