"""Verify a tentative supplied-tile position against a wider recentered fit."""

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..scoring import ARMS, distance_km

METHOD = "native_recenter_verify"
BOUNDARY = "Complete native GLRT with a second smooth fit on a centered 50 km square"
VERIFY_WIDTH_KM = 50.0
AGREEMENT_KM = 1.0


def inside(point, offer):
    center = offer["center"]
    frame = ecef_to_enu_matrix(*center)
    relative = geodetic_to_ecef_km(*point, 0) - geodetic_to_ecef_km(*center, 0)
    up = ecef_to_enu_matrix(*point)[2]
    facing = frame[2] @ up
    if facing <= 0:
        return False
    tangent = relative - up * ((frame[2] @ relative) / facing)
    return bool(max(abs(frame[:2] @ tangent)) <= offer.get("width_km", 25.0) / 2 + 1e-9)


def verify(first, offer, infer_expanded):
    """Keep the original endpoint only if both expanded-fit positions verify it."""
    decision = dict(first, boundary=BOUNDARY)
    if first["status"] != "ok":
        return decision, dict(attempted=False)
    positions = {arm: first["arms"][arm]["latlon"] for arm in ARMS}
    if any(point is None for point in positions.values()):
        raise ValueError("the original smooth solver must publish two calibration arms")
    expanded = dict(id=offer["id"] + "-verify", center=positions["c0"], width_km=VERIFY_WIDTH_KM)
    other = infer_expanded(expanded)
    points = {arm: other["arms"][arm]["latlon"] for arm in ARMS}
    shifts = {arm: distance_km(positions[arm], points[arm]) for arm in ARMS}
    contained = {arm: point is not None and inside(point, offer) for arm, point in points.items()}
    reason = None
    if other["status"] != "ok" or any(point is None for point in points.values()):
        reason = "expanded_fit_withheld"
    elif not all(contained.values()):
        reason = "expanded_fit_outside_original"
    elif max(shifts.values()) > AGREEMENT_KM:
        reason = "expanded_fit_disagrees"
    if reason:
        decision.update(
            status="withheld",
            reason=reason,
            arms={
                arm: dict(row, latlon=None, region_id=None) for arm, row in first["arms"].items()
            },
        )
    return decision, dict(
        attempted=True,
        offer=expanded,
        result=other,
        shifts_km=shifts,
        expanded_inside_original=contained,
    )
