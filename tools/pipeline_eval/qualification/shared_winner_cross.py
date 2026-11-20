"""Oracle winner swaps restricted to discordant jointly positive native probes."""

from collections import Counter
from math import isfinite

from .factor_cross import CFO, GATE, MARGIN, RANK, winner, wrapped
from .full_v5_check import ALIAS_HZ, FRAME_HZ
from .peak_support import BASINS

TREATMENTS = ("wide_alternative", "donor_required", "all_discordant")
AVAILABLE = "gated_wide_alternative"


def priority(candidate):
    return candidate[MARGIN], -candidate[RANK]


def physical(candidate):
    epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
    cfo = candidate[CFO]
    if not (isfinite(epoch) and isfinite(cfo)):
        raise ValueError("nonfinite epoch or CFO in native winner census")
    return epoch, cfo


def assess(wide, capture, availability):
    rate = wide["source"]["sample_rate_hz"]
    frame = round(rate / FRAME_HZ)
    seconds, hz = BASINS["strict"]
    samples = seconds * rate
    by_category = Counter()
    choices = []
    for i, (left, right, label) in enumerate(
        zip(wide["source"]["probes"], capture["source"]["probes"], availability, strict=True)
    ):
        if label != "11":
            continue
        candidates, donors = left["candidates"], right["candidates"]
        wi, ci = winner(candidates), winner(donors)
        if wi is None or ci is None:
            raise ValueError("jointly positive probe lacks a winner")
        t, f = physical(donors[ci])
        positions = [physical(c) for c in candidates]
        epochs = [j for j, (e, _) in enumerate(positions) if abs(wrapped(e - t, frame)) <= samples]
        matches = [j for j in epochs if abs(wrapped(positions[j][1] - f, ALIAS_HZ)) <= hz]
        if wi in matches:
            by_category["same_strict_family"] += 1
            continue
        gated = [j for j in matches if candidates[j][GATE] is True]
        if gated:
            category = AVAILABLE
        elif matches:
            category = "matching_wide_ungated"
        elif epochs:
            category = "epoch_nearby_wrong_cfo"
        else:
            category = "no_nearby_wide_epoch"
        by_category[category] += 1
        choices.append(
            dict(
                index=i,
                wide_winner=wi,
                capture_winner=ci,
                category=category,
                wide_alternative=max(gated, key=lambda j: priority(candidates[j]), default=None),
                nearby_epoch_candidates=len(epochs),
                strict_matching_candidates=len(matches),
                gated_alternatives=len(gated),
            )
        )
    return choices, dict(by_category)


def selected(case, mode):
    return mode == "all_discordant" or (case["category"] == AVAILABLE) == (
        mode == "wide_alternative"
    )


def replace(base, capture, choices, mode):
    if mode not in TREATMENTS:
        raise ValueError("unknown winner treatment")
    probes = base["source"]["probes"].copy()
    donor = capture["source"]["probes"]
    changed = 0
    for row in choices:
        if not selected(row, mode):
            continue
        i = row["index"]
        candidates = probes[i]["candidates"].copy()
        if mode == "wide_alternative":
            j = row["wide_alternative"]
        else:
            j = row["wide_winner"]
            candidates[j] = dict(
                donor[i]["candidates"][row["capture_winner"]], **{RANK: candidates[j][RANK]}
            )
        intended = priority(candidates[j])
        for k, current in enumerate(candidates):
            if current[GATE] is True and priority(current) > intended:
                candidates[k] = dict(current, **{GATE: False})
        if winner(candidates) != j:
            raise ValueError("intervention did not select the intended original measurement")
        probes[i] = dict(probes[i], candidates=candidates)
        changed += 1
    return dict(base, source=dict(base["source"], probes=probes)), changed
