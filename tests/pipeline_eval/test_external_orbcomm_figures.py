from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import acquisition_index, screening_figures
from tools.pipeline_eval.qualification.external_orbcomm_figures import mark_unavailable


def _prediction():
    return {
        "id": "query",
        "result": {
            "status": "ok",
            "boundary": "VHF pass fit",
            "metrics": {"rf_slope_identifiable": False},
            "arms": {
                "c0": {"latlon": [41.5, 2.1], "rf_rms_hz": 3.0},
                "fitted_c": {"latlon": None, "reason": "per_pass_offsets_span_rf_term"},
            },
        },
    }


def test_arm_status_preserves_the_source_reason_and_the_measured_zero_slope_arm():
    original = _prediction()
    display = mark_unavailable(original)
    assert original == _prediction()
    source = deepcopy(display)
    fitted = source["result"]["arms"]["fitted_c"]
    assert fitted.pop("status") == "unavailable"
    assert source == original

    queries = {"query": {"condition": "Containing", "recording": "test", "truth": [41.5, 2.1]}}
    predictions = {"candidate": {"query": display}}
    (fitted_mark,) = screening_figures._transfer_marks(queries, predictions, "fitted_c", version=2)
    (zero_mark,) = screening_figures._transfer_marks(queries, predictions, "c0", version=2)
    assert (fitted_mark.decision, fitted_mark.error_km) == ("unavailable", None)
    assert (zero_mark.decision, zero_mark.error_km) == ("published", 0.0)
    counts = acquisition_index.outcome([display["result"]], "fitted_c")
    assert counts["unavailable"] == 1 and counts["withheld"] == 0


@pytest.mark.parametrize(
    "values", [{"reason": ""}, {"latlon": [0, 0]}, {"forced_latlon": [0, 0]}, {"rf_rms_hz": 1.0}]
)
def test_unavailable_arm_requires_a_reason_and_cannot_carry_fit_values(values):
    original = _prediction()
    original["result"]["arms"]["fitted_c"].update(values)
    with pytest.raises(ValueError, match="unavailable calibration arm"):
        mark_unavailable(original)


def test_identifiable_calibration_cannot_be_marked_unavailable_by_the_orbcomm_projection():
    original = _prediction()
    original["result"]["metrics"]["rf_slope_identifiable"] = True
    with pytest.raises(ValueError, match="did not declare RF calibration unidentifiable"):
        mark_unavailable(original)
