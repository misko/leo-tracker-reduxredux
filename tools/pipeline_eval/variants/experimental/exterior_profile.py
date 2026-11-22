"""Sample the exact fixed-owner position objective across every offer face."""

from math import isfinite

import numpy as np


ARMS = ("c0", "fitted_c")
WIDTH_FRACTIONS = (1 / 512, 1 / 128, 1 / 32, 1 / 8, 1 / 2, 1, 2)
FACES = (("east", 0, 1), ("west", 0, -1), ("north", 1, 1), ("south", 1, -1))


def face_points(width_km, endpoints):
    """Use concentric squares and face normals through both selected endpoints."""
    half = width_km / 2
    if set(endpoints) != set(ARMS) or not isfinite(half) or half <= 0:
        raise ValueError("Both endpoints and a positive offered width are required")
    if any(len(xy) != 2 or not all(isfinite(x) and abs(x) <= half + 1e-9 for x in xy)
           for xy in endpoints.values()):
        raise ValueError("Endpoints must lie in the offered square")
    seen = set()
    rows = []
    for fraction in (0.0,) + WIDTH_FRACTIONS:
        distance = fraction * width_km
        for face, axis, sign in FACES:
            normal = half + distance
            tangent = {u * normal for u in (-1, -0.5, 0, 0.5, 1)}
            for endpoint in endpoints.values():
                for shift in (-width_km / 32, 0, width_km / 32):
                    tangent.add(float(np.clip(endpoint[1 - axis] + shift, -half, half)))
            for side in (("boundary",) if fraction == 0 else
                         ("exterior", "mirror") if fraction <= 1 / 2 else ("exterior",)):
                for along in sorted(tangent):
                    if side == "mirror" and abs(along) > half:
                        continue
                    across = sign * (half - distance if side == "mirror" else normal)
                    xy = (across, along) if axis == 0 else (along, across)
                    # Shared corners and intersecting inward normals are one location.
                    if xy not in seen:
                        seen.add(xy)
                        rows.append(dict(side=side, face=face, beyond_face_km=distance, xy_km=xy))
    return rows


def evaluate(region, grid, score):
    """Compare new probes and the full published inside grid, separately per arm."""
    rows = []
    for point in grid["points"]:
        xy = (point["east_km"], point["north_km"])
        rows.append(dict(side="grid", face=None, beyond_face_km=None, xy_km=xy,
                         latlon=point["latlon"], scores=point["scores"], failures=point["failures"]))
    seen = {row["xy_km"] for row in rows}
    for point in face_points(region.width_km, grid["endpoints"]):
        xy = point["xy_km"]
        if xy in seen:
            continue
        latlon = tuple(map(float, region.latlon(xy)))
        scores, failures = {}, {}
        for arm in ARMS:
            try:
                if not (-90 < latlon[0] < 90 and -180 <= latlon[1] <= 180):
                    raise ValueError("The probe leaves the local geographic frame")
                scores[arm] = float(score(arm, np.asarray(xy)))
                if not isfinite(scores[arm]):
                    raise ValueError("Nonfinite objective")
            except (ValueError, ArithmeticError, np.linalg.LinAlgError) as error:
                scores[arm] = None
                failures[arm] = str(error)
        rows.append(dict(point, latlon=latlon, scores=scores, failures=failures))

    def best(arm, points):
        available = [row for row in points if row["scores"][arm] is not None]
        if not available:
            return None
        point = min(available, key=lambda row: row["scores"][arm])
        return dict(xy_km=point["xy_km"], latlon=point["latlon"], face=point["face"],
                    beyond_face_km=point["beyond_face_km"], objective=point["scores"][arm])

    inside = [row for row in rows if row["side"] != "exterior"]
    outside = [row for row in rows if row["side"] == "exterior"]
    arms = {}
    for arm in ARMS:
        low, exterior = best(arm, inside), best(arm, outside)
        endpoint = next(row for row in rows if row["xy_km"] == tuple(grid["endpoints"][arm]))
        arms[arm] = dict(endpoint_objective=endpoint["scores"][arm],
                         edge_gap_km=region.width_km / 2 - max(map(abs, endpoint["xy_km"])),
                         inside_best=low, outside_best=exterior, inside_minus_outside=(
                             None if low is None or exterior is None else low["objective"] - exterior["objective"]),
                         shells=[best(arm, [row for row in outside if row["beyond_face_km"] == fraction * region.width_km])
                                 for fraction in WIDTH_FRACTIONS],
                         failed_points=sum(row["scores"][arm] is None for row in rows))
    return dict(arms=arms, points=rows)
