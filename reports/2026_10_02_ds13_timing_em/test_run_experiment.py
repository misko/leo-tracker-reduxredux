import json

import numpy as np
import pytest
from run_experiment import ROOT, association_summary, validate_request


def test_frozen_design_has_eighteen_cells_and_explicit_gates():
    protocol = json.loads((ROOT / "protocol.json").read_text())
    assert len(protocol["sessions"]) * len(protocol["models"]) * len(protocol["tolerances"]) == 18
    assert len(set(protocol["sessions"])) == 2
    for setting in protocol["tolerances"].values():
        assert setting["gate_hz"] == 3 * setting["sigma_hz"]


@pytest.mark.parametrize("session,method,tolerance", [
    ("outside", "direct", "medium"),
    ("scan-fw-911c4e5db9243281", "unknown", "medium"),
    ("scan-fw-911c4e5db9243281", "direct", "unknown"),
])
def test_outside_design_rejected(session, method, tolerance):
    protocol = json.loads((ROOT / "protocol.json").read_text())
    with pytest.raises(ValueError):
        validate_request(protocol, session, method, tolerance)


def test_association_accounting_uses_signal_and_clutter_not_raw_rows():
    result = association_summary({"association_probability": np.array([[0.8, 0.1], [0.2, 0.3]]),
                                  "expected_clutter_count": np.array([0.6])})
    assert result["expected_signal_peaks"] == pytest.approx(1.4)
    assert result["signal_fraction"] == pytest.approx(0.7)
    assert result["satellites_with_support_ge1"] == 1
