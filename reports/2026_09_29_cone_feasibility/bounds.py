"""Conservative cone exclusion over a position box and cached timing segments.

These are necessary-condition bounds, not an optimizer or a feasibility proof.
All retained candidates are included, even those failing a horizon gate.
"""

import math

import numpy as np


def geographic_envelope(center_lat_deg, east_limit_km=12.0, north_limit_km=12.0):
    """Bound receiver displacement and ENU-axis rotation in the frozen map.

    The map is lat=lat0+N/111.195 and lon=lon0+E/(111.195*cos(lat0)).
    On the zero-altitude WGS84 ellipsoid both principal curvature radii
    are <6400 km. Integrate the orthogonal latitude/longitude tangents
    along a straight path in coordinate space to bound ECEF displacement.
    ENU frames differ by latitude and longitude rotations, whose rotation
    angles obey the triangle inequality.
    """
    values = np.array([center_lat_deg, east_limit_km, north_limit_km], dtype=float)
    if not np.isfinite(values).all() or not -90 < center_lat_deg < 90:
        raise ValueError("Require a finite nonpolar center")
    if min(east_limit_km, north_limit_km) < 0:
        raise ValueError("Require nonnegative limits")
    lat = math.radians(center_lat_deg)
    dlat = math.radians(north_limit_km / 111.195)
    dlon = math.radians(east_limit_km / (111.195 * math.cos(lat)))
    if lat - dlat <= -math.pi / 2 or lat + dlat >= math.pi / 2:
        raise ValueError("Position box reaches a pole")
    max_cos = (
        1.0 if lat - dlat <= 0 <= lat + dlat else max(math.cos(lat - dlat), math.cos(lat + dlat))
    )
    return {
        "receiver_radius_km": 6400.0 * math.hypot(dlat, max_cos * dlon),
        "axis_rotation_deg": min(180.0, math.degrees(dlat + dlon)),
    }


def candidate_lower_bounds(
    positions,
    training_mask,
    receiver_ecef_km,
    axis_ecef,
    receiver_radius_km,
    axis_rotation_deg,
):
    """Lower-bound each candidate's worst training angle over the whole domain.

    positions is (candidate, ordered timing node, observation, xyz). Timing
    uses the existing linear interpolation between every adjacent pair.
    For each segment its midpoint is an anchor and half the endpoint
    distance bounds satellite displacement. Adding the receiver envelope
    gives a LOS perturbation radius. A ball of radius d about a LOS of
    length r subtends at most asin(d/r) when d<r; otherwise no exclusion
    is possible. Subtract this angle and the axis rotation envelope.

    Max over training observations is a segment-wise bound on the worst
    angle; min over segments covers every allowed common timing. Every
    candidate can still choose its own position and timing in this bound:
    a nonexcluded candidate need not participate in a common scan solution.
    """
    p = np.asarray(positions, dtype=float)
    mask = np.asarray(training_mask, dtype=bool)
    receiver = np.asarray(receiver_ecef_km, dtype=float)
    axis = np.asarray(axis_ecef, dtype=float)
    if p.ndim != 4 or p.shape[-1] != 3 or p.shape[0] == 0 or p.shape[1] < 2:
        raise ValueError("Require candidates, two timing nodes, observations, xyz")
    if mask.shape != (p.shape[2],) or not mask.any():
        raise ValueError("Require at least one training observation")
    if receiver.shape != (3,) or axis.shape != (3,):
        raise ValueError("Require receiver and axis vectors")
    if not all(np.isfinite(v).all() for v in (p, receiver, axis)):
        raise ValueError("Require finite geometry")
    if abs(float(np.linalg.norm(axis)) - 1) > 1e-12:
        raise ValueError("Require a unit axis")
    if not math.isfinite(receiver_radius_km) or receiver_radius_km < 0:
        raise ValueError("Require a nonnegative receiver radius")
    if not math.isfinite(axis_rotation_deg) or not 0 <= axis_rotation_deg <= 180:
        raise ValueError("Require a rotation bound in [0, 180]")
    left, right = p[:, :-1, mask], p[:, 1:, mask]
    los = (left + right) * 0.5 - receiver
    distance = np.linalg.norm(los, axis=-1)
    radius = receiver_radius_km + np.linalg.norm(right - left, axis=-1) * 0.5
    angle = np.degrees(np.arctan2(np.linalg.norm(np.cross(los, axis), axis=-1), los @ axis))
    informative = radius < distance
    ratio = np.divide(radius, distance, out=np.ones_like(radius), where=informative)
    perturbation = np.degrees(np.arcsin(np.clip(ratio, 0, 1)))
    lower = np.where(informative, angle - perturbation - axis_rotation_deg, 0.0)
    # Guard floating-point roundoff conservatively; this is not interval arithmetic.
    lower = np.maximum(0.0, lower - 1e-8)
    return lower.max(axis=2).min(axis=1)
