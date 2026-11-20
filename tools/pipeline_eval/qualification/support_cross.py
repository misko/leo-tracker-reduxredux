"""Cross exact probe-positive support while holding wide shared measurements fixed."""

from collections import Counter

from .factor_cross import GATE

CELLS = {
    "wide": (True, False),
    "remove": (False, False),
    "restore": (True, True),
    "both": (False, True),
}
CLOCK_FIELDS = ("clock_anchor", "delivery_clocks", "last_sample_counter", "schema_version")
AUTHORITY_FIELDS = (
    "session_id",
    "sample_rate_hz",
    "input_manifest_sha256",
    "raw_recording_authority_digest",
    "capture_start_utc_ns",
    "capture_end_utc_ns",
    "probe_ms",
    "radio_id",
    "stream_generation",
)
IDENTITY_FIELDS = ("visit_index", "receiver_id", "probe_index")


def positive(probe):
    return any(candidate[GATE] is True for candidate in probe["candidates"])


def metadata(probe):
    return {key: value for key, value in probe.items() if key != "candidates"}


def join(wide, capture):
    if any(wide[key] != capture[key] for key in CLOCK_FIELDS):
        raise ValueError("detectors disagree on acquisition clock or schema")
    if wide["provenance"]["excluded_windows"] != capture["provenance"]["excluded_windows"]:
        raise ValueError("detectors disagree on acquisition exclusions")
    left, right = wide["source"], capture["source"]
    if any(left[key] != right[key] for key in AUTHORITY_FIELDS):
        raise ValueError("detectors disagree on recording and sample authority")

    seen = set()
    roster = []
    for wide_probe, capture_probe in zip(left["probes"], right["probes"], strict=True):
        key = tuple(wide_probe[field] for field in IDENTITY_FIELDS)
        if key in seen or metadata(wide_probe) != metadata(capture_probe):
            raise ValueError("duplicate or mismatched hardware probe metadata")
        seen.add(key)
        support = f"{int(positive(wide_probe))}{int(positive(capture_probe))}"
        roster.append(support)
    return roster


def intervene(wide, capture, roster, cell):
    keep, restore = CELLS[cell]
    probes = []
    for source, donor, support in zip(
        wide["source"]["probes"], capture["source"]["probes"], roster, strict=True
    ):
        if support == "10" and not keep:
            cleared = [dict(candidate, **{GATE: False}) for candidate in source["candidates"]]
            probes.append(dict(source, candidates=cleared))
        elif support == "01" and restore:
            probes.append(dict(source, candidates=donor["candidates"]))
        else:
            probes.append(source)
    return dict(wide, source=dict(wide["source"], probes=probes))


def census(rows, roster):
    by_receiver_rf = {}
    for probe, label in zip(rows, roster, strict=True):
        key = f"{probe['receiver_id']}/{probe['channel']}/{probe['actual_rf_hz']}/{probe['edge']}"
        by_receiver_rf.setdefault(key, Counter())[label] += 1
    return dict(total=dict(Counter(roster)), by_receiver_rf=by_receiver_rf)
