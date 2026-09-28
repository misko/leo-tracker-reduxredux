"""Pure predeclared RX-guided, Doppler-ranked secondary selection."""

from __future__ import annotations

import math
from typing import Mapping


GUIDANCE_ARM = "D_plus_geometry"
RANKING_SCORE = "D"


def _coordinate(row: Mapping[str, object]) -> tuple[float, float]:
    east = float(row["east_km"])
    north = float(row["north_km"])
    if not math.isfinite(east) or not math.isfinite(north):
        raise ValueError("coordinates must be finite")
    return east, north


def select_rx_guided_doppler(branch: Mapping[str, object]) -> dict[str, object]:
    """Minimize D only over points evaluated by the joint-geometry arm."""
    arms = branch.get("arms")
    if not isinstance(arms, Mapping) or GUIDANCE_ARM not in arms:
        raise ValueError("branch lacks the frozen guidance arm")
    arm = arms[GUIDANCE_ARM]
    trace = arm.get("trace")
    if not isinstance(trace, list):
        raise ValueError("guidance arm lacks a trace")
    evaluated = []
    for event in trace:
        if event.get("event") == "evaluate":
            evaluated.append(_coordinate(event))
    if not evaluated:
        raise ValueError("guidance trace contains no evaluated points")
    if len(evaluated) != len(set(evaluated)):
        raise ValueError("guidance trace evaluates a coordinate more than once")
    declared_count = int(arm["evaluated_points"])
    if declared_count != len(evaluated):
        raise ValueError("guidance trace count disagrees with arm accounting")

    components = branch.get("point_components")
    if not isinstance(components, list):
        raise ValueError("branch lacks point components")
    by_coordinate = {}
    for point in components:
        coordinate = _coordinate(point)
        if coordinate in by_coordinate:
            raise ValueError("duplicate coordinate in point components")
        scores = point.get("scores")
        if not isinstance(scores, Mapping) or RANKING_SCORE not in scores:
            raise ValueError("point lacks Doppler score")
        score = float(scores[RANKING_SCORE])
        if not math.isfinite(score):
            raise ValueError("Doppler score must be finite")
        by_coordinate[coordinate] = point
    missing = [coordinate for coordinate in evaluated if coordinate not in by_coordinate]
    if missing:
        raise ValueError("guidance evaluation lacks a computed point component")

    chosen_coordinate = min(
        evaluated,
        key=lambda coordinate: (
            float(by_coordinate[coordinate]["scores"][RANKING_SCORE]),
            coordinate[0], coordinate[1],
        ),
    )
    chosen = dict(by_coordinate[chosen_coordinate])
    return {
        "selected": chosen,
        "evaluated_points": declared_count,
        "guidance_arm": GUIDANCE_ARM,
        "ranking_score": RANKING_SCORE,
        "selection": (
            "minimum D over exactly the coordinates evaluated by the "
            "D_plus_geometry arm; RX guides search coverage but does not rank "
            "the final coordinate"
        ),
        "admissible_coordinate_count": len(evaluated),
        "admissible_coordinates": [[east, north] for east, north in evaluated],
        "tie_break": "D, east_km, north_km ascending",
    }
