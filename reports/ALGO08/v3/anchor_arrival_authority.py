"""Read observable stereo and same-radio epoch support without selecting anchors."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import remainder
from pathlib import Path

from .anchor_delayed_history import HELD_PINS
from .anchor_only_history import ARMS, PINS, bind_native, decisions, load_cases, paired, read, seal, slot, stream
from .directed_donor import ADC, PERIOD, arrival_phase


PEER_SAMPLES = 2
CFO_ALIAS = ADC / 44
NEIGHBOR_LIMIT = 25_000_000


def epoch_difference(left, right):
    """Return RX1 minus RX0 on the physical frame circle for one simultaneous pair."""
    if (slot(left)[0], left["valid_start_counter"], stream(left)) != (
            slot(right)[0], right["valid_start_counter"], stream(right)):
        raise ValueError("A peer measurement must come from the same original stereo acquisition")
    counter = left["valid_start_counter"]
    a, b = (next(iter(row["candidates"]), None) for row in (left, right))
    if a is None or b is None:
        return None
    df = b["fractional_tracking_cfo_hz"] - a["fractional_tracking_cfo_hz"]
    return dict(samples=remainder(arrival_phase(counter, b) - arrival_phase(counter, a), PERIOD),
                signed_cfo_hz=df, folded_cfo_hz=remainder(df, CFO_ALIAS))


def modal_interval(values):
    """Maximum support in the inherited two-sample circular peer bin."""
    if not values:
        return dict(count=0, tied_sets=0, center=None, span=None)
    base = sorted(value % PERIOD for value in values)
    n = len(base)
    extended = base + [p + PERIOD for p in base]
    right = best = 0
    winners = []
    for left, start in enumerate(base):
        right = max(right, left + 1)
        while right < left + n and extended[right] - start <= 2 * PEER_SAMPLES:
            right += 1
        count = right - left
        if count > best:
            best, winners = count, []
        if count == best:
            winners.append((start, extended[right - 1]))
    alternatives = list(dict.fromkeys(winners))
    if len(alternatives) != 1:
        return dict(count=best, tied_sets=len(alternatives), center=None, span=None)
    start, end = alternatives[0]
    return dict(count=best, tied_sets=1, center=remainder((start + end) / 2, PERIOD), span=end-start)


def close_to(value, center):
    return abs(remainder(value - center, PERIOD)) <= PEER_SAMPLES


def inventory(mixed):
    ordered = list(decisions(mixed))
    donors = defaultdict(list)
    short_pairs = []
    anchors = []
    for (left, anchor), (right, peer_anchor) in zip(ordered[::2], ordered[1::2], strict=True):
        if anchor != peer_anchor:
            raise ValueError("An original stereo anchor cannot have a short peer")
        delta = epoch_difference(left, right)
        if anchor:
            anchors.extend((row, delta) for row in (left, right) if row["candidates"])
        else:
            if delta is not None:
                short_pairs.append((left["valid_start_counter"], delta["samples"]))
            for row in (left, right):
                if row["candidates"]:
                    donors[row["receiver_id"], *stream(row)].append(row["valid_start_counter"])
    midpoint = (mixed[0]["valid_start_counter"] + mixed[-1]["valid_start_counter"]) // 2
    halves = [[value for time, value in short_pairs if (time > midpoint) == later] for later in (False, True)]
    offsets = []
    for train, held in (halves, halves[::-1]):
        modal = modal_interval(train)
        center = modal["center"]
        offsets.append(dict(training=len(train), held=len(held), held_matches=None if center is None else
                            sum(close_to(value, center) for value in held), **modal))
    measured = []
    for row, delta in anchors:
        now = row["valid_start_counter"]
        times = donors[row["receiver_id"], *stream(row)]
        before = bisect_left(times, now) - bisect_left(times, now - NEIGHBOR_LIMIT)
        after = bisect_right(times, now + NEIGHBOR_LIMIT) - bisect_right(times, now)
        measured.append(dict(slot=slot(row), counter=now, stream=stream(row), candidate=row["candidates"][0],
                             peer=delta, short_before=before, short_after=after,
                             offset_fit_residuals=[None if delta is None or entry["center"] is None else
                                 remainder(delta["samples"] - entry["center"], PERIOD) for entry in offsets]))
    return dict(offsets=offsets, anchors=measured, full_anchor_lanes=sum(anchor for _, anchor in ordered),
                admitted_stereo_visits=len(ordered)//2, midpoint_counter=midpoint)


def score(data, stock, session, stock_owners, mixed_owners):
    observed = {slot(row): row["candidates"] for row in stock}
    installed_positive = sum(anchor and bool(row["candidates"]) for row, anchor in decisions(stock))
    totals = defaultdict(Counter)
    owned_extras = []
    for row in data["anchors"]:
        visit, radio = row["slot"]
        oid = "sha256:" + sha256(f"{session}:{radio}:{row['counter']}".encode()).hexdigest()
        reference = next(iter(observed[visit, radio]), None)
        groups = ["mixed_positive", "successor_only" if reference is None else "also_installed"]
        if reference is not None and any(oid in stock_owners[arm] for arm in ARMS):
            groups.append("installed_owned")
        if reference is None and any(oid in mixed_owners[arm] for arm in ARMS):
            groups.append("successor_only_owned")
            owned_extras.append(dict(row, observation_id=oid))
        peer = row["peer"]
        earlier, later = row["short_before"], row["short_after"]
        for name in groups:
            totals[name].update(total=1, peer=peer is not None, peer_within_uncalibrated_2=peer is not None and
                abs(peer["samples"]) <= PEER_SAMPLES, short_neighbors=bool(earlier or later),
                earlier_secant=earlier >= 2, bracket=bool(earlier and later),
                two_short_donors=earlier + later >= 2, any_peer_or_two_donors=peer is not None or earlier + later >= 2)
    return dict(totals={k: dict(count) for k, count in totals.items()}, owned_extras=owned_extras,
                anchor_lanes=data["full_anchor_lanes"], admitted_stereo_visits=data["admitted_stereo_visits"],
                all_installed_positives=installed_positive,
                offsets=data["offsets"],
                union_missing_both=sum(not row["peer"] and row["short_before"] + row["short_after"] < 2
                                      for row in data["anchors"]))


def audit(installed_0049, mixed_0049, installed_0407, mixed_0407):
    held = {k: read(path, HELD_PINS[k]) for k, path in (
        ("installed_0407", installed_0407), ("mixed_0407", mixed_0407))}
    unknown = {arm: set() for arm in ARMS}
    cases = load_cases(installed_0049, mixed_0049) | {
        "DS30-0407": (held["installed_0407"], held["mixed_0407"], unknown, unknown, None, None)}
    reports = {}
    for case, (stock, candidate, owners, candidate_owners, raw, frontier) in cases.items():
        source = candidate["source"]
        if source["sample_rate_hz"] != ADC:
            raise ValueError("The physical pilot cadence requires the original sample rate")
        planned = inventory(source["probes"])
        prediction = seal(planned)
        stock_rows, mixed = paired(stock, candidate)
        if raw is not None:
            kept = [r for r in mixed if r["visit_index"] < frontier]
            bind_native(raw, stock_rows[:len(kept)], kept)
        groups = score(planned, stock_rows, source["session_id"], owners, candidate_owners)
        reports[case] = dict(groups, observables_sha256=prediction, timing_present=source["timing"] is not None,
                             owners_available=raw is not None)
    return dict(schema="arrival-epoch-availability-v1", source_sha256=PINS | HELD_PINS, cases=reports,
                waveform_opens=0, capture_calls=0, solver_calls=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("installed_0049", "mixed_0049", "installed_0407", "mixed_0407", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    result = audit(args.installed_0049, args.mixed_0049, args.installed_0407, args.mixed_0407)
    with args.output.open("x") as file:
        json.dump(result, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")
