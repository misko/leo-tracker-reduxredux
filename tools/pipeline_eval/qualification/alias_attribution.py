"""Split raw winning CFO discrepancies into integer-branch and wrapped parts."""

from collections import Counter, defaultdict
from hashlib import sha256

from .factor_cross import CFO, winner, wrapped
from .peak_support import ALIAS_HZ, BASINS, FRAME_HZ, compare, family_probe, lane

CONDITIONS = ("stock", "alias", "residual", "joint", "null")


def delta(capture_cfo, wide_cfo):
    difference = capture_cfo - wide_cfo
    steps = round(difference / ALIAS_HZ)
    return steps, difference - steps * ALIAS_HZ


def observation_id(session, probe):
    return (
        "sha256:"
        + sha256(
            f"{session}:{probe['receiver_id']}:{probe['valid_start_counter']}".encode()
        ).hexdigest()
    )


def _epoch(row):
    return row["integer_epoch_sample"] + row["fractional_epoch_offset_samples"]


def match_winners(capture, wide):
    probes, target = (d["source"]["probes"] for d in (capture, wide))
    rate = wide["source"]["sample_rate_hz"]
    frame = round(rate / FRAME_HZ)
    counts, selected = Counter(), []
    for i, (a, b) in enumerate(zip(probes, target, strict=True)):
        if any(a[key] != b[key] for key in a if key != "candidates"):
            raise ValueError("different native acquisition probe support")
        left, right = a["candidates"], b["candidates"]
        j, k = winner(left), winner(right)
        counts["capture_positive"] += j is not None
        counts["wide_positive"] += k is not None
        counts["capture_only"] += j is not None and k is None
        counts["wide_only"] += k is not None and j is None
        if j is None or k is None:
            continue
        counts["both_positive"] += 1
        left_family, right_family = (family_probe(rows, frame, 2) for rows in (left, right))
        _, native = compare(left_family, right_family, frame, 2, BASINS["strict"][1])
        if any(outcome[0] != "same_winner_family" for outcome in native):
            counts["different_family_winners"] += 1
            continue
        if any(outcome[2] != 1 for outcome in native):
            counts["ambiguous_winner_families"] += 1
            continue
        capture_best, wide_best = left[j], right[k]
        raw_epoch = _epoch(capture_best) - _epoch(wide_best)
        epoch = wrapped(raw_epoch, frame)
        steps, residual = delta(capture_best[CFO], wide_best[CFO])
        if abs(epoch) > 2 or abs(residual) > BASINS["strict"][1]:
            counts["family_winner_members_outside"] += 1
            continue
        selected.append(
            dict(
                probe=i,
                capture_index=j,
                wide_index=k,
                steps=steps,
                residual_hz=residual,
                epoch_samples=epoch,
                raw_epoch_samples=raw_epoch,
                observation=observation_id(wide["source"]["session_id"], b),
                wide_cfo_hz=wide_best[CFO],
                capture_cfo_hz=capture_best[CFO],
            )
        )
        counts[f"alias_steps/{steps:+d}"] += 1
    counts["selected"] = len(selected)
    return selected, dict(counts)


def shuffled(document, selected):
    groups = defaultdict(list)
    rate = document["source"]["sample_rate_hz"]
    anchor = document["clock_anchor"]["sample_counter"]
    rows = document["source"]["probes"]
    for i, record in enumerate(selected):
        row = rows[record["probe"]]
        groups[(*lane(row), (row["valid_start_counter"] - anchor) // (30 * rate))].append(i)
    exchanged = [None] * len(selected)
    for ids in groups.values():
        offset = len(ids) // 2
        for j, dest in enumerate(ids):
            exchanged[dest] = selected[ids[(j + offset) % len(ids)]]
    return exchanged, sum(len(ids) == 1 for ids in groups.values())


def manipulate(document, selected, condition, *, exchanged=None):
    if condition not in CONDITIONS:
        raise ValueError("unknown CFO intervention")
    probes = document["source"]["probes"].copy()
    original = document["source"]["probes"]
    counts = Counter()
    if condition == "stock":
        return document, {}
    effects = exchanged if condition == "null" else selected
    for item, effect in zip(selected, effects, strict=True):
        idx = item["probe"]
        probe = original[idx]
        old_rows = probe["candidates"]
        j = item["wide_index"]
        if winner(old_rows) != j or old_rows[j][CFO] != item["wide_cfo_hz"]:
            raise ValueError("sealed physical winner changed")
        steps = 0 if condition == "residual" else effect["steps"]
        residual = 0 if condition == "alias" else effect["residual_hz"]
        adjusted = old_rows[j][CFO] + steps * ALIAS_HZ + residual
        if condition == "joint":
            adjusted = item["capture_cfo_hz"]
        counts["changed_winners"] += adjusted != old_rows[j][CFO]
        counts["nonzero_alias_changes"] += steps != 0
        if adjusted != old_rows[j][CFO]:
            new_rows = old_rows.copy()
            new_rows[j] = dict(old_rows[j], **{CFO: adjusted})
            probes[idx] = dict(probe, candidates=new_rows)
    return dict(document, source=dict(document["source"], probes=probes)), dict(counts)
