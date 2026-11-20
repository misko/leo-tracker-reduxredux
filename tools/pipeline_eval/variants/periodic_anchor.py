"""Select fixed reference sweeps and substitute complete detector visits."""

from itertools import groupby

PERIOD = 64
CHANNELS = tuple(range(1, 9))
ORDINARY_CONTROL = "ordinary-native-control"
REFERENCE_CONTROL = "capture-era-control"
TOP_LEVEL_SUPPORT = ("schema_version", "clock_anchor", "delivery_clocks", "last_sample_counter")
SOURCE_DETECTOR_FIELDS = {"probes", "analysis_manifest_sha256"}
PROVENANCE_SUPPORT = (
    "window_count",
    "processed_windows",
    "invalid_capture",
    "excluded_windows",
    "skipped_fast_score",
    "rf_mapping_authorities",
)


def reference_sweeps(schedule):
    """Count complete scheduled sweeps. Capture validity cannot change the sampling phase."""
    if any(row["visit"] != i for i, row in enumerate(schedule)):
        raise ValueError("schedule must cover each global visit exactly once in order")
    complete = []
    previous = -1
    for sweep, rows in groupby(schedule, lambda row: row["sweep"]):
        if sweep <= previous:
            raise ValueError("recorded sweep counter did not advance")
        visits = tuple(rows)
        if tuple(row["channel"] for row in visits) == CHANNELS and tuple(
            row["target_index"] for row in visits
        ) == tuple(range(8)):
            complete.append(visits)
        previous = sweep
    return tuple(complete[::PERIOD]), len(complete)


def _supports(probe):
    return {key: value for key, value in probe.items() if key != "candidates"}


def mix(ordinary, reference, schedule):
    """Return ordered hybrid probes after validating both complete detector archives."""
    if any(ordinary[key] != reference[key] for key in TOP_LEVEL_SUPPORT):
        raise ValueError("native archives disagree on timestamps or schema")
    first, second = ordinary["source"], reference["source"]
    if (first["sample_rate_hz"], first["probe_ms"], first["qualified"]) != (10_000_000, 20, True):
        raise ValueError("anchor factors require qualified 20 ms, 10 MS/s capture")
    if {k: v for k, v in first.items() if k not in SOURCE_DETECTOR_FIELDS} != {
        k: v for k, v in second.items() if k not in SOURCE_DETECTOR_FIELDS
    }:
        raise ValueError("native archives disagree on recording, geometry or IQ authority")
    if any(ordinary["provenance"][k] != reference["provenance"][k] for k in PROVENANCE_SUPPORT):
        raise ValueError("native archives disagree on capture exclusions or coverage")
    if len(schedule) != ordinary["provenance"]["window_count"]:
        raise ValueError("native archive does not contain the whole recorded schedule")
    sweeps, count = reference_sweeps(schedule)
    selected = {row["visit"] for sweep in sweeps for row in sweep}
    exclusions = {row["visit"]: row for row in ordinary["provenance"]["excluded_windows"]}
    for visit, row in exclusions.items():
        if any(row[k] != schedule[visit][k] for k in ("iq_sha256", "sample_start", "sample_end")):
            raise ValueError("excluded capture differs from authenticated scheduled visit")

    result = []
    changed = set()
    positive_counts = [0, 0, 0]
    support = {row["visit"]: [] for row in schedule if row["visit"] not in exclusions}
    for native, captured in zip(first["probes"], second["probes"], strict=True):
        if _supports(native) != _supports(captured):
            raise ValueError("detector archives have different probe keys or sample support")
        visit = native["visit_index"]
        row = schedule[visit]
        if (
            visit not in support
            or native["channel"] != row["channel"]
            or native["edge"] != row["edge"]
            or native["valid_start_counter"] != row["sample_start"]
            or native["probe_index"] != 0
            or native["probe_start_ms"] != 0
        ):
            raise ValueError("probe does not bind the scheduled dual-CI16 visit")
        support[visit].append(native["receiver_id"])
        probe = captured if visit in selected else native
        if probe != native:
            changed.add(visit)
        for i, candidate_source in enumerate((native, captured, probe)):
            positive_counts[i] += sum(
                candidate["passed_fractional_margin_gate"]
                for candidate in candidate_source["candidates"]
            )
        result.append(probe)
    if any(receivers != [0, 1] for receivers in support.values()):
        raise ValueError("valid visits require both original receiver rows")
    return result, dict(
        complete_sweeps=count,
        selected_sweeps=[s[0]["sweep"] for s in sweeps],
        selected_visits=sorted(selected),
        selected_valid_visits=len(selected - exclusions.keys()),
        selected_invalid_visits=len(selected & exclusions.keys()),
        changed_visits=sorted(changed),
        ordinary_positive=positive_counts[0],
        capture_era_positive=positive_counts[1],
        periodic_positive=positive_counts[2],
    )
