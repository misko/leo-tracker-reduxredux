from copy import deepcopy

import pytest
from audit_benchmark import model_matrix_issues, provenance_issues

MODELS = ("accepted", "rejected")


def complete_artifacts():
    fits = {
        "models": {
            "accepted": {
                "attempted": True,
                "model": "accepted",
                "status": "converged",
                "success": True,
                "initialization_provenance": "frozen seed",
                "rx_policy": "free",
            },
            "rejected": {
                "attempted": True,
                "model": "rejected",
                "status": "optimizer_failed",
                "success": False,
                "initialization_provenance": "fallback seed",
                "rx_policy": "fixed",
            },
        }
    }
    rows = {
        model: {
            "attempted": fitted["attempted"],
            "success": fitted["success"],
            "status": fitted["status"],
            "initialization_provenance": fitted["initialization_provenance"],
            "rx_policy": fitted["rx_policy"],
        }
        for model, fitted in fits["models"].items()
    }
    return fits, rows


def test_optimizer_rejection_is_an_attempted_complete_cell():
    fits, rows = complete_artifacts()

    assert model_matrix_issues(fits, rows, MODELS) == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing", "rejected: missing fit receipt"),
        ("unattempted", "rejected: never attempted"),
        ("error", "rejected: implementation/runtime error"),
    ],
)
def test_missing_unattempted_and_error_cells_are_incomplete(mutation, expected):
    fits, rows = complete_artifacts()
    if mutation == "missing":
        del fits["models"]["rejected"]
    elif mutation == "unattempted":
        fits["models"]["rejected"]["attempted"] = False
        rows["rejected"]["attempted"] = False
    else:
        fits["models"]["rejected"]["status"] = "error"
        rows["rejected"]["status"] = "error"

    assert expected in model_matrix_issues(fits, rows, MODELS)


@pytest.mark.parametrize("field", ["initialization_provenance", "rx_policy"])
def test_comparison_row_must_preserve_fit_provenance(field):
    fits, rows = complete_artifacts()
    rows = deepcopy(rows)
    rows["accepted"][field] = "different"

    assert f"accepted: {field} not preserved" in model_matrix_issues(fits, rows, MODELS)


def test_current_input_source_and_fit_receipt_digests_must_match():
    fits = {
        "input_sha256": {"bundle.json": "old-input"},
        "source_sha256": {"benchmark/models.py": "old-source"},
    }

    issues = provenance_issues(
        fits,
        {"bundle.json": "current-input"},
        {"benchmark/models.py": "current-source"},
        "current-fit",
        "old-fit",
    )

    assert issues == [
        "fit input has changed: bundle.json",
        "scientific implementation changed: benchmark/models.py",
        "comparison table does not bind current fit receipts",
    ]
