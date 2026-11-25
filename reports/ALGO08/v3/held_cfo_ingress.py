"""Opt-in held-odd CFO features using the verified ordinary Graph ingress."""

from collections import Counter
from math import isfinite
from operator import itemgetter

from leo.analysis.localization_v3.tracks import active_curvature, graph_tracks

from .held_cfo_features import (
    ADC, ALIAS, HERTZ, STEREO_FIELDS, STREAM, DerivedCfo, apply_shrink, forecasts_for,
    identity, released_donors, tag, winner,
)

INGRESS_FIELDS = ("receiver", "native_receiver_id", "channel", "time_s", "measured_cfo_hz",
                  "actual_rf_hz", "fractional_margin")
ingress_values = itemgetter(*INGRESS_FIELDS)
ingress_order = itemgetter("receiver", "channel", "time_s", "observation_id")


def bind_ingress(native, original_winners):
    """Verify all ordinary rows against the signed probes and keep their released sort order."""
    source, provenance = native["source"], native["provenance"]
    probes = iter(source["probes"])
    if not source["probes"]:
        raise ValueError("no GLRT probes")
    supplied, previous_key = {}, None
    for row in original_winners:
        key = ingress_order(row)
        oid = key[-1]
        if oid in supplied or previous_key is not None and key <= previous_key:
            raise ValueError("Expected distinct winning rows in ordinary Graph order")
        supplied[oid] = row
        previous_key = key

    origin = native["clock_anchor"]["sample_counter"]
    center_offset = source["probe_ms"] * .0005
    session = source["session_id"]
    sequence, previous_counter = Counter(), {}
    visits, held, retained, retained_ids = [], {}, {}, set()
    for left, right in zip(probes, probes, strict=False):
        key = tuple(left[name] for name in STREAM)
        counter, visit = left["valid_start_counter"], left["visit_index"]
        if ([left["receiver_id"], right["receiver_id"]] != [0, 1]
                or any(left[name] != right[name] for name in STEREO_FIELDS)
                or key in previous_counter and previous_counter[key] >= counter):
            raise ValueError("Expected the original ordered stereo opportunities")
        index = sequence[key]
        sequence[key] += 1
        previous_counter[key] = counter
        visits.append(visit)
        time_s = (counter-origin)/ADC + center_offset
        for row in (left, right):
            radio = row["receiver_id"]
            oid = tag(f"{session}:{radio}:{counter}".encode())
            if oid in held or oid in retained:
                raise ValueError("Repeated signed stereo opportunity")
            factor = winner(row)
            observation = supplied.pop(oid, None)
            if factor is not None:
                expected = (radio+1, radio, int(row["channel"]), time_s, float(factor[HERTZ]),
                            float(row["actual_rf_hz"]), float(factor["fractional_margin"]))
                if (observation is None or ingress_values(observation) != expected
                        or not isfinite(expected[4])):
                    raise ValueError("Ordinary Graph row differs from the signed winning probe")
            elif observation is not None:
                raise ValueError("Ordinary Graph row has no gated winning probe")
            lane = dict(id=oid, counter=counter, short=index % 8 != 0, row=row, lane=(*key, radio))
            if index % 2:
                held[oid] = lane
            else:
                retained[oid] = dict(lane, factor=factor)
                if factor is not None:
                    retained_ids.add(oid)

    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    if (2*len(visits) != len(source["probes"]) or visits != sorted(visits)
            or sorted(visits+excluded) != list(range(provenance["window_count"]))
            or len(visits) != provenance["processed_windows"]):
        raise ValueError("Admitted and excluded visits must partition the signed acquisition")
    if supplied:
        raise ValueError("Ordinary Graph rows have unknown signed observation IDs")
    return [row for row in original_winners if row["observation_id"] in retained_ids], held, retained


def derive(native, approved_graph_config, original_winners):
    """Derive the frozen CFO sidecar from authenticated native data and ordinary winners."""
    if (native["source"]["sample_rate_hz"] != ADC
            or approved_graph_config.alias_spacing_hz != ALIAS):
        raise ValueError("The frozen rule requires its original ADC and Graph alias conventions")
    rows, held, retained = bind_ingress(native, original_winners)
    tracks, assigned = graph_tracks(rows, approved_graph_config, source_id="SCAN")
    curved = sum(active_curvature(track) for track in tracks)
    donors = released_donors({"tracks": tracks}, retained)
    if donors.keys() & held.keys():
        raise ValueError("Held observations reached the masked Graph")
    forecasts, eligibility = forecasts_for(held, retained, donors)
    edits, gates = apply_shrink(held, forecasts)
    return DerivedCfo(identity(native), edits, dict(tracks=len(tracks), assigned=assigned, curved_tracks=curved),
                      forecasts, eligibility, gates)
