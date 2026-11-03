import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location("waveform_association_test", Path(__file__).with_name("association_audit.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_invisible_candidate_cannot_win_and_visible_mass_normalizes():
    index, row = audit.candidate_summary([100., np.log(.7), np.log(.3)],
                                         [False, True, True], [1, 65512, 2])
    assert index == 1 and row["norad"] == 65512
    assert row["conditional_row_mass"] == pytest.approx(.7)


def test_missing_visible_support_is_not_reported_as_identification():
    with pytest.raises(AssertionError):
        audit.candidate_summary([0.], [False], [65512])
