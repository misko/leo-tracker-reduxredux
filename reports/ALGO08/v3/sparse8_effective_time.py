"""Research opt-in for effective Graph time on the qualified sparse 20/8 ms receiver."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


SELECTED_RECIPE = "sha256:ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"
CONVENTION = "short native verifier equal-frame centroid relative to the full verifier at the exported frame epoch"
CLOCK_SOURCE_PINS = {
    "localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
}


def source_rows(native, selection):
    from anchor_exposure import enroll
    from full_short_run import SPARSE_EIGHT_MS_RECIPE_SHA
    from leo.contracts.digests import canonical_digest
    from sparse8_time_math import RATE, centroid

    if not isinstance(selection, dict):
        raise ValueError("missing held selector witness")
    recipe = selection.get("receiver_recipe")
    if (canonical_digest(recipe) != SELECTED_RECIPE
            or selection.get("detector_recipe_sha256") != SELECTED_RECIPE
            or selection.get("parent_detector_sha256") != "sha256:"+SPARSE_EIGHT_MS_RECIPE_SHA
            or native["provenance"]["detector_sha256"] != SELECTED_RECIPE
            or selection.get("native_sha256") != canonical_digest(native)
            or selection.get("refinement_calls") != 0):
        raise ValueError("unexpected detector or unbound native aperture provenance")
    route = selection.get("choice", {}).get("route")
    if route not in {"unfiltered", "history"}:
        raise ValueError("unsupported held selector action")
    source = native["source"]
    if not source["qualified"] or source["probe_ms"] != 20 or source["sample_rate_hz"] != RATE:
        raise ValueError("unexpected native sample rate or nominal probe")
    rows = {}
    for probe, (_, _, rx, _, aperture, _) in zip(source["probes"], enroll(native), strict=True):
        candidates = probe["candidates"]
        if not candidates:
            continue
        factor, = candidates
        if (factor["passed_fractional_margin_gate"] is not True
                or aperture == "short" and factor["candidate_rank"] != 0):
            raise ValueError("unexpected measured factor at its enrolled aperture")
        start = probe["valid_start_counter"]
        identity = "sha256:" + sha256(f"{source['session_id']}:{rx}:{start}".encode()).hexdigest()
        nominal = (start-native["clock_anchor"]["sample_counter"]) / RATE + .010
        offset = 0.
        if aperture == "short":
            short, _, _ = centroid(factor, True)
            long, _, _ = centroid(factor, False)
            offset = short-long
        rows[identity] = (nominal, offset, float(factor["fractional_tracking_cfo_hz"]))
    if type(selection.get("selected")) is not int or selection["selected"] != len(rows):
        raise ValueError("saved factor count differs from the signed selector")
    return route, rows


@contextmanager
def binding(native, selection, audit):
    from leo.analysis import glrt_frequency_input
    from leo.analysis.localization_v3 import tracks
    from leo.contracts.digests import canonical_digest
    from sparse8_time_math import graph_rows

    audit.update(requested=True, applied=False, convention=CONVENTION)
    begun = process_time_ns(), perf_counter_ns()
    try:
        imported = (tracks, glrt_frequency_input)
        if any(sha256(Path(module.__file__).read_bytes()).hexdigest() != pin
               for module, pin in zip(imported, CLOCK_SOURCE_PINS.values(), strict=True)):
            raise ValueError("unsupported installed Graph time semantics")
        route, corrections = source_rows(native, selection)
    except (KeyError, OSError, TypeError, ValueError) as problem:
        audit.update(reason=str(problem), preparation_cpu_ns=process_time_ns()-begun[0],
                     preparation_elapsed_ns=perf_counter_ns()-begun[1])
        yield
        return
    counts = Counter(round(shift*1e6, 4) for _, shift, _ in corrections.values())
    audit.update(route=route, native_sha256=selection["native_sha256"], offsets_us=dict(sorted(counts.items())),
                 source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                 preparation_cpu_ns=process_time_ns()-begun[0],
                 preparation_elapsed_ns=perf_counter_ns()-begun[1])
    original = tracks.winning_observations

    def adjusted(packet):
        rows, metadata = original(packet)
        if "reason" in audit:
            return rows, metadata
        started = process_time_ns(), perf_counter_ns()
        try:
            if packet is not native and canonical_digest(packet) != selection["native_sha256"]:
                raise ValueError("Graph presented a different signed packet")
            corrected = graph_rows(rows, corrections)
        except ValueError as problem:
            if audit["applied"]:
                raise
            audit["reason"] = str(problem)
            return rows, metadata
        graph_digest = canonical_digest(corrected)
        if audit["applied"] and audit["corrected_graph_input_sha256"] != graph_digest:
            raise ValueError("The corrected solver presented inconsistent Graph evidence")
        audit.update(applied=True, corrected_graph_input_sha256=graph_digest,
                     application_cpu_ns=process_time_ns()-started[0],
                     application_elapsed_ns=perf_counter_ns()-started[1])
        return corrected, metadata

    with patch.object(tracks, "winning_observations", adjusted):
        yield
