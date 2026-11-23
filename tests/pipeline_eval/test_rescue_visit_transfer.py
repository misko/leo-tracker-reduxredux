import pytest

from reports.ALGO08.v3.rescue_visit_transfer import check_trial


@pytest.mark.parametrize(
    "failed, expected",
    [(True, {"c0": 10, "fitted_c": 25}), (False, {"c0": 25, "fitted_c": 25})],
)
def test_charges_both_arms_if_first_has_no_terminal_failure(failed, expected):
    arms, witness = {}, {}
    for arm, visits in (("c0", 2), ("fitted_c", 3)):
        bad = failed and arm == "c0"
        arms[arm] = {
            "history": [{"fit": {"evaluations": visits}} for _ in range(5)],
            "minimum_gate_slack": -1.0 if bad else 0.1,
            "final_phase_change_s": 0.001,
            "gates": {"tracks": [{"compatible": not bad}]},
            "linear_gates": [],
            "corrected_selection_loss": 1.0,
            "RMS_hz": 20.0,
        }
        witness[arm] = {
            "corrected_loss": 1.0,
            "RMS_hz": 20.0,
            "failed_curved": int(bad),
            "failed_predictive": 0,
            "paired_valid": not failed,
        }
    trial = {
        "constrained_refinement_attempted": True,
        "arms": arms,
        "paired_valid": not failed,
        "replacements": [],
    }
    assert check_trial(trial, witness)["ordered_visits"] == expected
    witness["c0"]["RMS_hz"] = 30.0
    with pytest.raises(ValueError, match="differs"):
        check_trial(trial, witness)
