"""Use two independently associated positions to route a trusted-tile request."""

from time import perf_counter

from ..scoring import ARMS, distance_km

METHOD = "native_agreement_cascade"
LIMIT_KM = 0.5
BOUNDARY = "Complete native GLRT through paired native agreement and lazy trusted-tile compact fit"


def route(smooth, anchors, threshold_km=LIMIT_KM):
    distances = {
        arm: distance_km(
            smooth.get("arms", {}).get(arm, {}).get("latlon"),
            anchors.get("arms", {}).get(arm, {}).get("latlon"),
        )
        for arm in ARMS
    }
    agrees = all(value is not None and value <= threshold_km for value in distances.values())
    published = smooth["status"] == anchors["status"] == "ok"
    return dict(
        route="fast" if agrees and published else "fallback",
        threshold_km=threshold_km,
        agreement_km=distances,
        reason="paired_agreement"
        if published and agrees
        else (
            "disagreement"
            if published and all(v is not None for v in distances.values())
            else "insufficient_publication"
        ),
    )


def execute(smooth, anchors, compact):
    """Call compact only after the two genuine native decisions require it."""
    stages = {}
    started = perf_counter()

    def call(name, worker):
        before = perf_counter()
        row = worker()
        stages[name] = perf_counter() - before
        return row

    clock = call("smooth-clock", smooth)
    curve = call("curve-anchors", anchors)
    decision = route(clock["result"], curve["result"])
    selected = clock if decision["route"] == "fast" else call("compact-secant", compact)
    return dict(
        result=dict(selected["result"], boundary=BOUNDARY),
        route=decision,
        stages_wall_s=stages,
        calls=list(stages),
        worker_wall_s=perf_counter() - started,
        smooth=clock,
        anchors=curve,
        compact=selected if decision["route"] == "fallback" else None,
    )
