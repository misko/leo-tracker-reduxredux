import numpy as np
from probe_algo03_age_covered_position import scale_multiplier


def test_phase_scale_ratio_applies_learned_floor_and_midpoint_age():
    receipts=[dict(old_new_alignment_s=2.,age_s=850.,previous_epoch_gap_s=2000.),
              dict(old_new_alignment_s=None,age_s=850.,previous_epoch_gap_s=None)]
    ratio=scale_multiplier(receipts,np.array([2.,1.]),dict(floor_s=.5,gain=.5))
    np.testing.assert_allclose(ratio,[np.hypot(.5,.5)/2,.5])
