from copy import deepcopy

from tools.ds7_clock_recovery_v2 import corrected_qualification, declared_condition_limit


def _result() -> dict:
    return {
        "status": "qualified",
        "projected_rank": {"rank": 5, "columns": 5, "condition_number": 38.5},
        "cases": [
            {
                "injected_native_hz_s": [0.0, 0.0],
                "qualified": True,
                "boundary_hit": False,
            }
        ],
    }


def test_corrected_qualification_rejects_boundary_hit() -> None:
    result = deepcopy(_result())
    result["cases"][0]["boundary_hit"] = True

    audit = corrected_qualification(result, 1_000.0)

    assert audit["corrected_status"] == "unqualified"
    assert audit["cases"][0]["boundary_free"] is False


def test_corrected_qualification_rejects_excess_condition_number() -> None:
    result = deepcopy(_result())
    result["projected_rank"]["condition_number"] = 1_000.01

    audit = corrected_qualification(result, 1_000.0)

    assert audit["corrected_status"] == "unqualified"
    assert audit["condition_within_limit"] is False


def test_corrected_qualification_accepts_interior_well_conditioned_result() -> None:
    audit = corrected_qualification(_result(), 1_000.0)

    assert audit["corrected_status"] == "qualified"
    assert audit["condition_within_limit"] is True


def test_declared_condition_limit_is_read_from_gate_text() -> None:
    gate = {
        "admission_gates": {
            "identifiability": "unregularized design has condition number <= 1000"
        }
    }

    assert declared_condition_limit(gate) == 1_000.0
