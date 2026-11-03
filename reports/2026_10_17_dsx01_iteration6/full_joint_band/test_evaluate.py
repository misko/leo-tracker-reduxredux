import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("joint_full_evaluation", HERE / "evaluate.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def test_paired_denominator_new_lost_and_rms_share_same_intersection():
    old = dict(
        associated=np.array([True, False, True, True]),
        residual_hz=np.array([3.0, 8.0, 4.0, 20.0]),
        satellite_number=np.array([1, 2, 3, 4]),
    )
    new = dict(
        associated=np.array([True, True, False, True]),
        residual_hz=np.array([6.0, 5.0, 9.0, 10.0]),
        satellite_number=np.array([9, 2, 3, 4]),
    )
    stats = evaluation.paired(old, new, np.array([True, True, True, False]))
    assert stats["observations"] == 3 and stats["assigned"] == 2
    assert stats["new"] == 1 and stats["lost"] == 1 and stats["retained"] == 1
    assert stats["intersection_original_rms_hz"] == 3.0
    assert stats["intersection_current_rms_hz"] == 6.0
    assert stats["retained_identity_changes"] == 1


def test_empty_association_remains_in_fixed_denominator():
    state = dict(
        associated=np.array([False, False]),
        residual_hz=np.array([10.0, 20.0]),
        satellite_number=np.array([1, 2]),
    )
    stats = evaluation.paired(state, state, np.array([True, True]))
    assert stats["observations"] == 2 and stats["assigned"] == 0
    assert stats["associated_rms_hz"] is None
    assert stats["intersection_original_rms_hz"] is None
