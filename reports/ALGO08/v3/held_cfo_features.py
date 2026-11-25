"""Candidate-only held-odd CFO features for the released observation boundary."""

from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite, remainder

from leo.analysis.localization_v3.tracks import prepare_tracks

ADC = 10_000_000
ALIAS = 1/4.4e-6
BIN_HZ = ADC/(44*512)
PERIOD = 40_000/3
HERTZ = "fractional_tracking_cfo_hz"
STREAM = ("edge", "channel", "actual_rf_hz")
STEREO_FIELDS = (*STREAM, "valid_start_counter", "visit_index")


@dataclass(frozen=True)
class DerivedCfo:
    native_identity: tuple
    edits: dict
    masked_graph: dict
    forecasts: dict
    eligibility: dict
    gates: dict


def identity(native):
    source = native["source"]
    return (source["session_id"], source["raw_recording_authority_digest"], source["input_manifest_sha256"],
            source["analysis_manifest_sha256"], native["provenance"]["detector_sha256"])


def tag(body):
    return "sha256:" + sha256(body).hexdigest()


def winner(row):
    return max((candidate for candidate in row["candidates"] if candidate["passed_fractional_margin_gate"] is True),
               key=lambda candidate: (candidate["fractional_margin"], -candidate["candidate_rank"]), default=None)


def masked_stereo(native):
    """Port the frozen stereo mask while keeping the sealed historical sources intact."""
    source, provenance = native["source"], native["provenance"]
    session = source["session_id"]
    sequence, previous = Counter(), {}
    visits, masked, held, retained = [], [], {}, {}
    probes = source["probes"]
    for left, right in zip(probes[::2], probes[1::2], strict=True):
        key = tuple(left[name] for name in STREAM)
        counter, visit = left["valid_start_counter"], left["visit_index"]
        if ([left["receiver_id"], right["receiver_id"]] != [0, 1]
                or any(left[name] != right[name] for name in STEREO_FIELDS)
                or key in previous and previous[key] >= counter):
            raise ValueError("Expected the original ordered stereo opportunities")
        index = sequence[key]
        sequence[key] += 1
        previous[key] = counter
        visits.append(visit)
        for row in (left, right):
            radio = row["receiver_id"]
            oid = tag(f"{session}:{radio}:{counter}".encode())
            if oid in held or oid in retained:
                raise ValueError("Repeated signed stereo opportunity")
            lane = dict(id=oid, counter=counter, short=index % 8 != 0, row=row, lane=(*key, radio))
            if index % 2:
                held[oid] = lane
                masked.append(dict(row, candidates=[]))
            else:
                retained[oid] = dict(lane, factor=winner(row))
                masked.append(row)
    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    if (visits != sorted(visits) or sorted(visits+excluded) != list(range(provenance["window_count"]))
            or len(visits) != provenance["processed_windows"]):
        raise ValueError("Admitted and excluded visits must partition the signed acquisition")
    digest = tag(json.dumps(["cancellation", source["raw_recording_authority_digest"],
                             provenance["detector_sha256"][7:], masked],
                            sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode())
    return dict(native, source=dict(source, probes=masked, analysis_manifest_sha256=digest),
                provenance=dict(provenance, run_id="odd-short-graph-"+digest[7:39])), held, retained


def released_donors(packet, retained):
    """Read the stock Graph's unambiguous piece order and native alias lifts."""
    occurrences = Counter()
    pieces = []
    for track in packet["tracks"]:
        by_index = dict(zip(sorted(track["indices"]), zip(track["observation_ids"], track["values"], strict=True),
                            strict=True))
        for number, piece in enumerate(track["pieces"]):
            rows = []
            for ordinal, index in enumerate(sorted(piece["indices"])):
                oid, lifted = by_index[index]
                row = retained[oid]
                turns = (float(lifted)-row["factor"][HERTZ])/ALIAS
                lift = round(turns)
                if abs(lift-turns) > 1e-8:
                    raise ValueError("Masked Graph frequency differs from signed CFO and its integer alias")
                occurrences[oid] += 1
                rows.append(dict(row, piece=(track["key"], number), ordinal=ordinal, lift=lift))
            pieces.append(rows)
    return {row["id"]: row for piece in pieces if all(occurrences[r["id"]] == 1 for r in piece) for row in piece}


def arrival(counter, factor):
    phase = (3*counter % 40_000)/3
    return (phase+factor["integer_epoch_sample"]+factor["fractional_epoch_offset_samples"]) % PERIOD


def interpolate(left, middle, right):
    a, b = middle-left["counter"], right["counter"]-middle
    if not (0 < a <= ADC and 0 < b <= ADC and 4*a*b <= ADC**2):
        return None, "spacing"
    if left["lift"] != right["lift"]:
        return None, "ambiguous_alias_branch"
    lift = left["lift"]
    lower, upper = (row["factor"][HERTZ]+lift*ALIAS for row in (left, right))
    if abs(upper-lower)*ADC > 8_000*(a+b):
        return None, "slope"
    start, end = (arrival(row["counter"], row["factor"]) for row in (left, right))
    delta = remainder(end-start, PERIOD)
    if not isfinite(delta) or abs(delta) == PERIOD/2:
        return None, "ambiguous_arrival_arc"
    fraction = a/(a+b)
    lifted = lower+fraction*(upper-lower)
    return dict(cfo_hz=lifted-lift*ALIAS, lifted_cfo_hz=lifted, graph_alias_lift=lift,
                arrival=(start+fraction*delta) % PERIOD, donors=[left["id"], right["id"]],
                donor_counters=[left["counter"], right["counter"]],
                donor_full=[not row["short"] for row in (left, right)], left_wait_samples=a, right_wait_samples=b), "proposed"


def forecasts_for(held, retained, donors):
    nearby = defaultdict(list)
    for oid, row in retained.items():
        if row["factor"] is not None:
            nearby[row["lane"]].append((row["counter"], oid))
    counters = {lane: [counter for counter, _ in entries] for lane, entries in nearby.items()}
    forecasts, eligibility = {}, Counter()
    for oid, target in held.items():
        lane, at = target["lane"], target["counter"]
        neighbors = nearby.get(lane, ())
        index = bisect_left(counters.get(lane, ()), at)
        if index == 0 or index == len(neighbors):
            eligibility["not_bracketed"] += 1
            continue
        left, right = (donors.get(k) for _, k in neighbors[index-1:index+1])
        if left is None or right is None:
            eligibility["unassigned_or_ambiguous"] += 1
        elif left["piece"] != right["piece"] or right["ordinal"] != left["ordinal"]+1:
            eligibility["different_or_nonadjacent_piece"] += 1
        else:
            forecast, reason = interpolate(left, at, right)
            eligibility[reason] += 1
            if forecast is not None:
                forecasts[oid] = forecast
    return forecasts, dict(eligibility)


def apply_shrink(held, forecasts):
    edits, gates = {}, Counter()
    for oid, forecast in forecasts.items():
        target = held[oid]
        factor = winner(target["row"])
        if factor is None:
            gates["target_empty"] += 1
            continue
        value = factor[HERTZ]
        delta = forecast["cfo_hz"]-value
        if not isfinite(delta) or abs(delta) > BIN_HZ:
            gates["more_than_one_bin"] += 1
            continue
        gates["eligible"] += 1
        edits[oid] = dict(original_hz=value, forecast_hz=forecast["cfo_hz"], updated_hz=value+delta/2,
                          arrival=arrival(target["counter"], factor))
    return edits, dict(gates)


def derive(native, approved_graph_config):
    """Return sidecar features for an authenticated 20/8 packet and its approved TrackConfig.

    Both receiver rows of every held visit are blank before the released Graph
    and its winner selection. The original target supplies only the final
    innovation gate, measured arrival and measured CFO.
    """
    if (native["source"]["sample_rate_hz"] != ADC
            or approved_graph_config.alias_spacing_hz != ALIAS):
        raise ValueError("The frozen rule requires its original ADC and Graph alias conventions")
    masked, held, retained = masked_stereo(native)
    packet = prepare_tracks(masked, approved_graph_config)
    donors = released_donors(packet, retained)
    if donors.keys() & held.keys():
        raise ValueError("Held observations reached the masked Graph")
    forecasts, eligibility = forecasts_for(held, retained, donors)
    edits, gates = apply_shrink(held, forecasts)
    graph = dict(tracks=len(packet["tracks"]), assigned=packet["graph_points"], curved_tracks=len(packet["curved_indices"]))
    return DerivedCfo(identity(native), edits, graph, forecasts, eligibility, gates)


def apply_to_winners(native, original_observations, features):
    """Return the corrected ordinary Graph rows, leaving native data and rows untouched."""
    if identity(native) != features.native_identity:
        raise ValueError("Derived CFO belongs to a different authenticated native packet")
    if not features.edits:
        return original_observations
    seen, updated = set(), []
    for row in original_observations:
        oid = row["observation_id"]
        change = features.edits.get(oid)
        if change is not None:
            if row["measured_cfo_hz"] != change["original_hz"] or oid in seen:
                raise ValueError("Derived CFO does not match the original winning observation")
            seen.add(oid)
            row = dict(row, measured_cfo_hz=change["updated_hz"])
        updated.append(row)
    if seen != features.edits.keys():
        raise ValueError("Some derived CFO observations are absent from the ordinary Graph input")
    return updated
