from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reports/ALGO08/v3'))

from cumulative_grid_projection import saved_detector
from named_south_transfer_score import depth_intervals, face_distances


def test_saved_named_receiver_uses_only_installed_pin_and_authenticated_inventory():
    specification = {'detector_sha256':'installed'}
    assert saved_detector({}, specification, 'mixed') == 'mixed'
    with pytest.raises(ValueError, match='authenticated'):
        saved_detector({'receiver':'named-v3'}, specification, 'mixed')
    with pytest.raises(ValueError, match='reviewed receiver'):
        saved_detector({'receiver':'unverified','saved_inventory':'inventory.json'}, specification, 'mixed')
    job = dict(receiver='named-v3', saved_inventory='index.json', detector_sha256='untrusted')
    assert saved_detector(job, specification, 'mixed') == specification['detector_sha256']


def test_east_face_signed_clearance_and_nearest_face_in_solver_frame():
    bounds = {'center':[0.,0.], 'width_km':25.}
    inside = face_distances(bounds, [0., 12.4/111.32])
    assert inside['east_face_inward_m'] == pytest.approx(100.)
    assert inside['east_face_is_nearest']
    outside = face_distances(bounds, [0., 12.6/111.32])
    assert outside['east_face_inward_m'] == pytest.approx(-100.)
    assert outside['east_face_is_nearest']
    north = face_distances(bounds, [12.6/111., 12.4/111.32])
    assert north['nearest_face_inward_m'] < 0 < north['east_face_inward_m']
    assert not north['east_face_is_nearest']
    assert face_distances(bounds, None) is None


def test_depth_interval_distinguishes_joint_and_per_arm_thresholds():
    intervals = depth_intervals([800., 1100.], [600., 900.])
    assert not intervals['single_threshold_for_each_arm']['possible']
    assert intervals['reject_if_either_below'] == dict(lower_exclusive_m=600., upper_inclusive_m=800., possible=True)
    assert intervals['reject_if_both_below'] == dict(lower_exclusive_m=900., upper_inclusive_m=1100., possible=True)
    assert intervals['individual']['fitted_c'] == intervals['reject_if_both_below']
    assert not depth_intervals([100.,100.], [100.,100.])['reject_if_either_below']['possible']
    assert depth_intervals([800.,1100.], [None,None]) is None
