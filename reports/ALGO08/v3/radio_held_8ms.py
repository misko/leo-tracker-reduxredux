"""Apply the original held-cycle score separately to each antenna."""

from collections import Counter
from hashlib import sha256
from math import isfinite
from pathlib import Path


def radio_routes(gains):
    if set(gains) != {0, 1} or any(not isfinite(gain) for gain in gains.values()):
        raise ValueError("Expected two finite original held-cycle gains")
    return {radio: "history" if gains[radio] > 0 else "unfiltered" for radio in (0, 1)}


def project(original, history, routes):
    selected = []
    for measured, kept in zip(original, history, strict=True):
        radio = measured["receiver_id"]
        if kept != dict(measured, candidates=kept["candidates"]) or any(
            proposal not in measured["candidates"] for proposal in kept["candidates"]
        ):
            raise ValueError("History changed a signed opportunity or introduced a candidate")
        selected.append(kept if routes[radio] == "history" else measured)
    return selected


def select(original, recipe):
    from anchor_exposure import bind
    from anchor_holds import history_rows
    from continued_cfo_trial import rebinding
    from eight_ms_held_fit import select as global_select
    from empty_bootstrap import bind_native, clock, now
    from leo.contracts.digests import canonical_digest

    start = now()
    global_packet, global_evidence = global_select(original, recipe)
    routes = radio_routes(global_evidence["choice"]["log_score_gain_by_radio"])
    measured = original["source"]["probes"]
    authority = dict(
        routes=routes, choice=global_evidence["choice"],
        parent_native_sha256=global_evidence["parent_native_sha256"],
        parent_detector_sha256=global_evidence["parent_detector_sha256"],
        global_native_sha256=global_evidence["native_sha256"],
        global_detector_sha256=global_evidence["detector_recipe_sha256"],
        global_selector=global_evidence["selector"],
    )
    if len(set(routes.values())) == 1:
        if routes[0] != global_evidence["choice"]["route"]:
            raise ValueError("Same-sign routing diverged from the original wrapper")
        packet, detector_recipe = global_packet, global_evidence["receiver_recipe"]
        detector, native = (global_evidence[key] for key in ("detector_recipe_sha256", "native_sha256"))
    else:
        rows = project(measured, history_rows(measured), routes)
        # The original wrapper and all sources used for its held scores remain
        # in the recipe; the per-radio projection has its own signed identity.
        detector_recipe = dict(global_evidence["receiver_recipe"], per_antenna_held=dict(
            source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            parent_native_sha256=authority["parent_native_sha256"],
            parent_detector_sha256=authority["parent_detector_sha256"],
            rule="history on a receiver iff its held Bernoulli log gain is strictly positive",
        ))
        packet = rebinding(original, rows, detector_recipe)
        bind(original, packet)
        detector, native = canonical_digest(detector_recipe), canonical_digest(packet)
        source = original["source"]
        bind_native(packet, source["session_id"], source["input_manifest_sha256"], detector[7:], expected=native)
    rows = packet["source"]["probes"]
    return packet, dict(
        authority, detector_recipe_sha256=detector, native_sha256=native, receiver_recipe=detector_recipe,
        observed=sum(bool(row["candidates"]) for row in measured),
        selected_by_radio=dict(Counter(row["receiver_id"] for row in rows if row["candidates"])),
        selected=sum(bool(row["candidates"]) for row in rows), refinement_calls=0, selector=clock(start),
    )
