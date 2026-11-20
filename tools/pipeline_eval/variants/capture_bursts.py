"""Clock-only balanced periodic and burst admissions for the capture-era detector."""

from collections import Counter

from .selective_capture import visit_pairs

HORIZON = 832
CHANNELS = range(1, 9)
CALLS = {"periodic": 12, "burst": 12, "periodic_high": 52, "burst_high": 52}


def clock_slots(mode, channel):
    if channel not in CHANNELS or mode not in CALLS:
        raise ValueError("invalid RF channel or capture duty")
    phase = channel - 1
    if mode == "periodic":
        return range(3 + 3 * phase, HORIZON, 72)[:12]
    if mode == "periodic_high":
        return range(1 + 2 * phase, HORIZON, 16)
    bases = (1, 400, 813) if mode == "burst" else range(0, HORIZON, 64)
    offset = 2 * phase if mode == "burst" else 5 + 3 * phase
    return tuple(base + offset + j for base in bases for j in range(4))


def scheduled_visits(metadata, mode):
    slots = {channel: set(clock_slots(mode, channel)) for channel in CHANNELS}
    seen = Counter()
    admitted = []
    previous = -1
    for visit, channel in metadata:
        if visit <= previous or channel not in slots:
            raise ValueError("the RF opportunities must follow the chronological scan")
        if seen[channel] in slots[channel]:
            admitted.append(visit)
        seen[channel] += 1
        previous = visit
    if any(seen[channel] < HORIZON for channel in CHANNELS):
        raise ValueError("the capture lacks the frozen per-channel opportunity horizon")
    if len(admitted) != len(CHANNELS) * CALLS[mode]:
        raise ValueError("the matched original-call budget was not spent exactly")
    return admitted


def inventories(document):
    """Read and validate complete stereo acquisition metadata without candidate fields."""
    provenance = document["provenance"]
    visits = []
    for visit, (left, right) in visit_pairs(document["source"]["probes"]):
        keys = ("channel", "actual_rf_hz", "edge", "valid_start_counter", "payload_start_sample")
        if any(left[k] != right[k] for k in keys) or left["channel"] not in CHANNELS:
            raise ValueError("a stereo visit disagrees about its RF or sample clock")
        visits.append((visit, left["channel"]))
    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    full = provenance["window_count"]
    if (
        len(document["delivery_clocks"]) != full
        or len(visits) != provenance["processed_windows"]
        or len(visits) + len(excluded) != full
        or {v for v, _ in visits}.union(excluded) != set(range(full))
    ):
        raise ValueError("the original capture lacks a complete disjoint valid/excluded ledger")
    return visits


def select_document(document, admitted, identity):
    """Keep original metadata and replace unmeasured candidates with an empty list."""
    include = set(admitted)
    rows = document["source"]["probes"]
    count = sum(p["visit_index"] in include for p in rows)
    if count != 2 * len(admitted):
        raise ValueError("the admitted schedule is not a subset of full stereo visits")
    selected = [p if p["visit_index"] in include else dict(p, candidates=[]) for p in rows]
    return dict(
        document,
        source=dict(document["source"], probes=selected, analysis_manifest_sha256=identity),
        provenance=dict(document["provenance"], run_id="capture-bursts-" + identity[7:33]),
    )
