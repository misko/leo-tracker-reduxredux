"""Project saved receiver evidence onto fixed antenna, channel and time schedules."""

from collections import Counter

from leo.contracts.digests import canonical_digest


def time_arcs(native):
    """Publish both antennas in the first and last quarters of the capture clock."""
    source = native["source"]
    probes = source["probes"]
    start = native["clock_anchor"]["sample_counter"]
    duration = native["last_sample_counter"] - start
    if source["sample_rate_hz"] != 10_000_000 or duration <= 0:
        raise ValueError("Expected a positive 10 MS/s capture")
    retained = []
    warmup = 0
    for row in probes:
        elapsed = row["valid_start_counter"] - start
        if not 0 <= elapsed < duration:
            raise ValueError("Probe lies outside the sealed capture clock")
        if 4 * elapsed < duration or 4 * elapsed >= 3 * duration:
            retained.append(row)
        elif 4 * (elapsed + 80_000_000) >= 3 * duration:
            # Native measurements in this interval recreate the last eight seconds
            # of candidate history. They never become observations for the fit.
            warmup += 1
    digest = canonical_digest(["first-last-quarters", source["analysis_manifest_sha256"], retained])
    return dict(native, source=dict(source, probes=retained, analysis_manifest_sha256=digest),
                provenance=dict(native["provenance"], scope="first-last-quarters-replay",
                                run_id="time-arcs-"+digest[7:39], warmup_lanes=warmup,
                                processed_windows=len({r["visit_index"] for r in retained}),
                                parent_detection_sha256=source["analysis_manifest_sha256"]))


def project(native, flip, policy="one-antenna-per-channel"):
    """Keep full-history selections. Alternating visits requires a separate raw check."""
    if flip not in (0, 1):
        raise ValueError("Expected one of two antenna assignments")
    if policy not in ("one-antenna-per-channel", "stereo-alternate-channels", "alternate-visits-full-history"):
        raise ValueError("Unknown channel policy")
    source = native["source"]
    pairs = source["probes"]
    if len(pairs) % 2:
        raise ValueError("Expected complete dual-antenna visits")
    selected = []
    visits = Counter()
    for first, second in zip(pairs[::2], pairs[1::2], strict=True):
        if ({first["receiver_id"], second["receiver_id"]} != {0, 1} or
                any(first[k] != second[k] for k in ("visit_index", "channel", "actual_rf_hz", "valid_start_counter"))):
            raise ValueError("The two probes must represent the same visit")
        lane = (int(first["channel"]) + flip) % 2
        if policy == "one-antenna-per-channel":
            selected.append(first if first["receiver_id"] == lane else second)
        elif policy == "alternate-visits-full-history":
            key = first["channel"], first["actual_rf_hz"]
            if visits[key] % 2 == flip:
                selected.extend((first, second))
            visits[key] += 1
        elif lane == 0:
            selected.extend((first, second))
    digest = canonical_digest([policy, flip, source["analysis_manifest_sha256"], selected])
    return dict(native, source=dict(source, probes=selected, analysis_manifest_sha256=digest),
                provenance=dict(native["provenance"], scope=policy+"-replay",
                                processed_windows=len({row["visit_index"] for row in selected}),
                                run_id="channel-lane-" + digest[7:39], channel_assignment_flip=flip,
                                parent_detection_sha256=source["analysis_manifest_sha256"]))
