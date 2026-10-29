import numpy as np
from audit_reentry_warning_signals import angular_summary


def test_spherical_rank_handles_north_wrap_and_rigid_rotation():
    a=np.deg2rad([-2,0,2]);peers=np.column_stack((np.sin(a),np.cos(a),np.zeros(3)))
    target=np.array([0.,1.,0.]);r=angular_summary(target,peers)
    assert r['centroid_distance_deg']<1e-6
    assert r['nearest_peer_deg']<1e-6
    rotation=np.array([[0,0,1],[1,0,0],[0,1,0]])
    rotated=angular_summary(target@rotation,peers@rotation)
    np.testing.assert_allclose(r['peer_radii_deg'],rotated['peer_radii_deg'])
    far=angular_summary(np.array([1.,0.,0.]),peers)
    assert far['centroid_rank_percent']==100
    assert far['nearest_peer_deg']>85
