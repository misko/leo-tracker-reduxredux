"""Interleave stereo RF visits without changing the underlying capture timeline."""

from collections import defaultdict, deque

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.carrier_continuation import Continuation


MODES = ("full", "fixed", "guarded")
RF_FIELDS = ("edge", "channel", "actual_rf_hz")
COUNTER = "valid_start_counter"
STRONG = 0.1


def _rf(row):
    return tuple(row[field] for field in RF_FIELDS)


def _supported(history, counter):
    donors = [(when, margin) for when, margin in history
              if margin is not None and 0 < counter - when <= 80_000_000]
    return (len(donors) >= 3 and counter - donors[0][0] >= 4_000_000
            and donors[-1][1] >= STRONG)


def masked(native, mode, *, reselect=False):
    """Erase skipped candidate rows. Optional continuation uses only available input factors."""
    if mode not in MODES:
        raise ValueError(f"Unknown aperture mask: {mode}")
    source = native["source"]
    if source["sample_rate_hz"] != 10_000_000:
        raise ValueError("Expected the v3 10 MS/s capture clock")
    original = source["probes"]
    pairs = list(zip(original[::2], original[1::2], strict=True))
    opportunities = defaultdict(list)
    previous_visit, previous_counter = -1, -1
    for first, second in pairs:
        visit, counter = first["visit_index"], first[COUNTER]
        if (visit <= previous_visit or counter <= previous_counter
                or (first["receiver_id"], second["receiver_id"]) != (0, 1)
                or any(first[field] != second[field] for field in (*RF_FIELDS, COUNTER, "visit_index"))):
            raise ValueError("Expected two chronologically ordered antenna rows per visit")
        opportunities[_rf(first)].append(visit)
        previous_visit, previous_counter = visit, counter
    proposed = {visit for visits in opportunities.values() for visit in visits[4:-1:4]}
    history = defaultdict(lambda: (deque(maxlen=12), deque(maxlen=12)))
    continuation = Continuation() if reselect else None
    projected, dropped, escalated = [], [], []
    for first, second in pairs:
        visit, counter = first["visit_index"], first[COUNTER]
        past = history[_rf(first)]
        omit = mode != "full" and visit in proposed
        if omit and mode == "guarded" and not all(_supported(lane, counter) for lane in past):
            escalated.append(visit)
            omit = False
        if omit:
            dropped.append(visit)
        for row, lane in zip((first, second), past, strict=True):
            candidates = [] if omit else row["candidates"]
            # The quality gate sees factors available at measured visits. A
            # reselection may reject a factor as a localization observation.
            lane.append((counter, max((f["fractional_margin"] for f in candidates), default=None)))
            if continuation is not None:
                _, keep, _ = continuation.select(dict(row, candidates=candidates))
                candidates = [] if keep is None else [candidates[keep]]
            projected.append(dict(row, candidates=candidates))

    detector = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    digest = canonical_digest(["cancellation", source["raw_recording_authority_digest"],
                               detector, projected])
    omitted = set(dropped)
    available = sum(len(row["candidates"]) for row in original if row["visit_index"] not in omitted)
    audit = dict(
        policy=mode, reselect=reselect, opportunities=len(pairs), rf_groups=len(opportunities),
        proposed=len(proposed), dropped=dropped, escalated=escalated,
        original_observations=sum(len(row["candidates"]) for row in original),
        surviving_opportunity_observations=available,
        resulting_observations=sum(len(row["candidates"]) for row in projected),
        probe_sha256=canonical_digest(projected),
    )
    if projected == original:
        return native, audit
    # This private saved solver input retains each original opportunity row,
    # full capture authority, clock and quality-admission accounting.
    return dict(native, source=dict(source, probes=projected, analysis_manifest_sha256=digest),
                provenance=dict(native["provenance"], run_id="blind-compact-" + digest[7:39])), audit
