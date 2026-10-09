"""Regression for dictionary and dataclass fitter terminal receipts."""

import numpy as np
import pytest
from supplement_terminal_audit import EXPECTED_ERROR, normalize_terminal, supplement

from leo.analysis.regional_position_fit import PositionFit


def terminal():
    return PositionFit(np.zeros(10), 12.0, 5.0, 20.0, 0.0001, True, False, "stationary", 5, 0.01)


def test_dataclass_and_mapping_terminal_normalize_identically():
    mapped = normalize_terminal(terminal())
    assert normalize_terminal(mapped) == mapped
    assert mapped["converged"] and mapped["vector"] == [0] * 10


def test_preserved_postfit_diagnostic_error_is_separate_from_fit_convergence():
    fit = normalize_terminal(terminal())
    audit = dict(objective=12.0, stationarity=0.0001, feasible=True)
    receipt = dict(
        status="failed",
        error=EXPECTED_ERROR,
        fit=fit,
        diagnostics=dict(terminal=terminal()),
        gradient_audits=dict(returned=audit),
    )
    result = supplement(receipt)
    assert result["numerical_fit_status"] == "qualified"
    assert result["original_status"] == "failed" and result["new_optimizer_calls"] == 0
    assert receipt["status"] == "failed"


def test_different_terminal_cannot_borrow_returned_audit():
    fit = normalize_terminal(terminal())
    changed = dict(fit, vector=[1] + [0] * 9)
    receipt = dict(
        status="complete",
        fit=fit,
        diagnostics=dict(terminal=changed),
        gradient_audits=dict(returned=dict(objective=12.0, stationarity=0.0001, feasible=True)),
    )
    with pytest.raises(AssertionError, match="Different states"):
        supplement(receipt)
