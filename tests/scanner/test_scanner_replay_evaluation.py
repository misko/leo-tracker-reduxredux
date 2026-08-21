from __future__ import annotations

import numpy as np

from leo.scanner import ScanDecision, ScannerReferenceLabel
from tools.evaluate_scanner_replay_dataset import _complex_frame, _outcome, _rates


def test_complex_frame_reconstructs_live_scanner_values_losslessly() -> None:
    values = np.array(
        [[[-2048, 2047], [17, -19]], [[0, 1], [-1, 0]]],
        dtype="<i2",
    )

    reconstructed = _complex_frame(values)

    assert reconstructed.dtype == np.dtype(np.complex64)
    assert reconstructed.tolist() == [
        [complex(-2048, 2047), complex(17, -19)],
        [complex(0, 1), complex(-1, 0)],
    ]
    assert not reconstructed.flags.writeable


def test_reference_decision_outcomes_and_rates() -> None:
    assert _outcome(ScannerReferenceLabel.ACTIVE, ScanDecision.ACTIVE) == "true_positive"
    assert _outcome(ScannerReferenceLabel.ACTIVE, ScanDecision.NO_DETECTION) == "false_negative"
    assert _outcome(ScannerReferenceLabel.QUIET, ScanDecision.ACTIVE) == "false_positive"
    assert _outcome(ScannerReferenceLabel.QUIET, ScanDecision.NO_DETECTION) == "true_negative"
    assert _outcome(ScannerReferenceLabel.QUIET, ScanDecision.INCONCLUSIVE) == "inconclusive"
    assert _rates(
        {
            "true_positive": 3,
            "true_negative": 6,
            "false_positive": 2,
            "false_negative": 1,
        }
    ) == {
        "accuracy": 0.75,
        "recall": 0.75,
        "specificity": 0.75,
        "false_positive_rate": 0.25,
    }
