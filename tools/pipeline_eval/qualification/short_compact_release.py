"""Make a causal paired-arm decision from independent completed block results."""

from math import cos, radians

from ..scoring import ARMS, distance_km
from .short_compact import no_fix

MAX_AGREEMENT_KM = 1.0
MAX_RADIUS_KM = 2.0
MAX_CONDITION = 25.0
MIN_ORBITS = 3
MIN_POINTS = 36
INTERIOR_KM = 0.020
CAPTURE_END_S = 300.0


def margin(point, tile):
    lat, lon = tile["center"]
    north = (point[0] - lat) * 111.0
    east = (point[1] - lon) * 111.32 * cos(radians(lat))
    return tile.get("width_km", 25.0) / 2 - max(abs(east), abs(north))


def support_reasons(row, arm):
    result = row["result"]
    if result["status"] != "ok":
        return [f"compact_{result['status']}"]
    point = result["arms"][arm]["latlon"]
    shape = result["metrics"].get("terminal_local_geometry", {}).get(arm)
    if shape is None or "geometry_error" in shape or point != shape["latlon"]:
        return ["missing_terminal_geometry"]
    radius, condition = shape["nominal_radius95_km"], shape["information_condition"]
    return [
        key
        for key, failed in (
            ("orbital_support", len(shape["orbits"]) < MIN_ORBITS),
            ("point_support", shape["active_points"] < MIN_POINTS),
            ("local_radius", radius is None or not (0 < radius <= MAX_RADIUS_KM)),
            ("local_condition", condition is None or not (1 <= condition <= MAX_CONDITION)),
            ("tile_face", radius is None or margin(point, row["tile"]) <= INTERIOR_KM + radius),
        )
        if failed
    ]


def compare(earlier, later):
    if (
        earlier["support"]["last_visit"] >= later["support"]["first_visit"]
        or earlier["support"]["seconds"][-1] > later["support"]["seconds"][0]
    ):
        raise ValueError("independent checks must use nonintersecting physical visits")
    if any(earlier[k] != later[k] for k in ("id", "native_sha256", "catalog_sha256", "tile")):
        raise ValueError("adjacent block fits do not share the exact supplied science inputs")
    checks = {}
    for arm in ARMS:
        old, new = (row["result"]["arms"][arm]["latlon"] for row in (earlier, later))
        separation = distance_km(old, new)
        checks[arm] = dict(
            separation_km=separation,
            agrees=separation is not None and separation <= MAX_AGREEMENT_KM,
            earlier_reasons=support_reasons(earlier, arm),
            later_reasons=support_reasons(later, arm),
        )
    qualified = all(
        row["agrees"] and not row["earlier_reasons"] and not row["later_reasons"]
        for row in checks.values()
    )
    return qualified, checks


def decide(blocks):
    """Use block-local evidence and the fixed schedule, without full-capture results."""
    if [row["name"] for row in blocks] != ["0", "1", "2"]:
        raise ValueError("all three scheduled block outcome envelopes are required")
    finish = [0.0, 0.0]
    checkpoints = []
    reached = 0
    total_cpu = 0.0
    for i, row in enumerate(blocks):
        wall = row["worker_wall_s"] + row["input_preparation_wall_s"]
        finish = [
            max(a, b) + wall for a, b in zip(finish, row["support"]["available_s"], strict=True)
        ]
        total_cpu += row["worker_cpu_s"]
        reached = i + 1
        if not i:
            continue
        qualified, arms = compare(blocks[i - 1], row)
        before_deadline = finish[-1] < CAPTURE_END_S
        shared = dict(
            nominal_checkpoint_s=(i + 1) * 75,
            completion_elapsed_s=finish,
            paired_science_gate=qualified,
            completes_before_schedule=before_deadline,
            arms=arms,
        )
        checkpoints.append(shared)
        if qualified and before_deadline:
            result = dict(
                row["result"],
                boundary="Two disjoint compact v5 blocks with a prospective paired release gate",
            )
            return result, dict(
                released=True,
                chosen_block=row["name"],
                last_worker_end_elapsed_s=finish,
                speculative_cpu_s=total_cpu,
                run_blocks=reached,
                checks=checkpoints,
            )
    return (
        no_fix("withheld", "no_qualified_early_pair"),
        dict(
            released=False,
            chosen_block=None,
            last_worker_end_elapsed_s=finish,
            speculative_cpu_s=total_cpu,
            run_blocks=reached,
            checks=checkpoints,
        ),
    )
