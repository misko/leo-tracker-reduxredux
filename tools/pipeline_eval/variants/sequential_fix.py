"""Decide whether a pair of cumulative compact forecasts can release a fix."""

from ..scoring import ARMS, distance_km

CHECKPOINTS = (210, 255)
MAX_DISPLACEMENT_KM = 0.35
MIN_SHARED_ORBITS = 4
MIN_REFRESHED_ORBITS = 2
MIN_POINTS = 36
MAX_RADIUS_KM = 2.0
MAX_CONDITION = 25.0
FACE_RESERVE_KM = 0.020


def release(earlier, current):
    """Evaluate the two available estimates without the fallback or score inputs."""
    if (earlier["checkpoint"], current["checkpoint"]) != CHECKPOINTS:
        raise ValueError("outcomes must be from the registered cumulative checkpoints")
    if any(earlier[k] != current[k] for k in ("id", "tile", "catalog_sha256")):
        raise ValueError("outcomes do not share their recording, offer and causal catalogue")
    old, new = (row["support"] for row in (earlier, current))
    if old["first_visit"] != 0 or new["first_visit"] != 0 or old["last_visit"] >= new["last_visit"]:
        raise ValueError("both outcomes must contain increasing complete visits from capture start")

    left, right = (row["result"] for row in (earlier, current))
    checks = {}
    for arm in ARMS:
        first, last = [r["metrics"].get("terminal_support", {}).get(arm, {}) for r in (left, right)]
        points = [r["arms"][arm]["latlon"] for r in (left, right)]
        distance = distance_km(*points)
        old_orbits, new_orbits = (r.get("latest_by_norad", {}) for r in (first, last))
        shared = sorted(old_orbits.keys() & new_orbits.keys())
        refreshed = [key for key in shared if new_orbits[key] > CHECKPOINTS[0]]
        radius = last.get("nominal_radius95_km")
        condition = last.get("information_condition")
        xy = last.get("east_north_km", [])
        half_width = current["tile"].get("width_km", 25.0) / 2
        margin = half_width - max(map(abs, xy)) if len(xy) == 2 else None
        reasons = [
            name
            for name, ok in (
                ("positions", left["status"] == right["status"] == "ok" and None not in points),
                ("disagreement", distance is not None and distance <= MAX_DISPLACEMENT_KM),
                ("shared_orbits", len(shared) >= MIN_SHARED_ORBITS),
                ("refreshed_orbits", len(refreshed) >= MIN_REFRESHED_ORBITS),
                ("point_support", last.get("active_points", 0) >= MIN_POINTS),
                ("local_radius", radius is not None and 0 < radius <= MAX_RADIUS_KM),
                ("local_condition", condition is not None and 1 <= condition <= MAX_CONDITION),
                (
                    "tile_face",
                    radius is not None and margin is not None and margin > radius + FACE_RESERVE_KM,
                ),
            )
            if not ok
        ]
        checks[arm] = dict(
            reasons=reasons,
            displacement_km=distance,
            shared_norads=shared,
            refreshed_norads=refreshed,
            nominal_radius95_km=radius,
            information_condition=condition,
            tile_face_clearance_km=margin,
        )
    return dict(released=all(not check["reasons"] for check in checks.values()), arms=checks)
