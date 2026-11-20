"""Truth-free geometry diagnostic using exact, archived capture winning measurements."""

from collections import defaultdict
from hashlib import sha256

from ..variants.selective_capture import same_support
from .factor_cross import CFO, GATE, MARGIN, RANK, winner
from .hard_pilots_eval import TOLERANCE, classify, near_epoch, support

MODES = ("availability", "matched_availability", "placebo", "conflicts")
SALT = "fixed-both-missing-v1"


def census(documents):
    capture, stock, fifth = (documents[k] for k in ("capture", "four", "five"))
    for fixed in (stock, fifth):
        same_support(capture, fixed)
        if support(capture) != support(fixed):
            raise ValueError("diagnostic requires identical complete physical acquisition")
    branches = [d["source"]["probes"] for d in (capture, stock, fifth)]
    choices = {k: [] for k in ("availability", "placebo", "conflicts")}
    for index, (original, left, right) in enumerate(zip(*branches, strict=True)):
        donor_index = winner(original["candidates"])
        if donor_index is None:
            continue
        donor = original["candidates"][donor_index]
        four, five = [classify(donor, p["candidates"]) for p in (left, right)]
        missing_both = not any(a["category"] == "physical_gated" for a in (four, five))
        if missing_both:
            kind = "conflicts" if four["any_gate"] else "availability"
        elif not four["any_gate"] and five["category"] == "physical_gated":
            kind = "placebo"
        else:
            continue
        choices[kind].append(
            dict(
                index=index,
                visit=original["visit_index"],
                lane=original["receiver_id"],
                channel=original["channel"],
                edge=original["edge"],
                negative_cfo=donor[CFO] < 0,
                original_winner=donor_index,
                stock_category=four["category"],
                fifth_category=five["category"],
            )
        )
    return choices


def matched(ident, available, placebo):
    """Pair the nearest visits within exact lane/tune/sign strata without reuse."""
    left, right = defaultdict(list), defaultdict(list)
    for group, rows in ((left, available), (right, placebo)):
        for p in rows:
            stratum = p["lane"], p["channel"], p["edge"], p["negative_cfo"]
            group[stratum].append(p)

    def order(pair):
        a, b = pair
        key = f"{SALT}:{ident}:{a['index']}:{b['index']}".encode()
        return abs(a["visit"] - b["visit"]), sha256(key).digest()

    pairs = []
    for key in sorted(left.keys() & right.keys()):
        candidates = sorted(((a, b) for a in left[key] for b in right[key]), key=order)
        used_a, used_b = set(), set()
        for a, b in candidates:
            if a["index"] in used_a or b["index"] in used_b:
                continue
            pairs.append((a, b))
            used_a.add(a["index"])
            used_b.add(b["index"])
            if len(used_a) == min(len(left[key]), len(right[key])):
                break
    return pairs


def select(ident, documents):
    choices = census(documents)
    pairs = matched(ident, choices["availability"], choices["placebo"])
    roster = {
        "availability": choices["availability"],
        "matched_availability": [a for a, _ in pairs],
        "placebo": [b for _, b in pairs],
        "conflicts": choices["conflicts"],
    }
    return roster, [[a["index"], b["index"]] for a, b in pairs], len(choices["placebo"])


def priority(candidate):
    return candidate[MARGIN], -candidate[RANK]


def transplant(stock, capture, chosen, mode):
    """Preserve donor fields/rank and force its selection only at listed physical probes."""
    if mode not in MODES:
        raise ValueError("unexpected winner-transplant cell")
    base = stock["source"]["probes"]
    output = base.copy()
    for row in chosen:
        index = row["index"]
        entering = base[index]["candidates"]
        current_index = winner(entering)
        if (current_index is not None) != (mode == "conflicts"):
            raise ValueError("a cell mixed addition with replacement of an admitted measurement")
        donor = capture["source"]["probes"][index]["candidates"][row["original_winner"]]
        if donor[GATE] is not True or output[index] is not base[index]:
            raise ValueError("each changed probe requires one exact original gated winner")
        if current_index is not None:
            active = entering[current_index]
            if near_epoch(active, donor) and abs(active[CFO] - donor[CFO]) <= TOLERANCE:
                raise ValueError("shared positive already has the physical donor winner")
        new = []
        for prior in entering:
            if prior[RANK] == donor[RANK]:
                continue
            admitted = prior[GATE] is True and priority(prior) <= priority(donor)
            new.append(prior if admitted == prior[GATE] else dict(prior, **{GATE: admitted}))
        new.append(donor)
        new.sort(key=lambda row: row[RANK])
        if new[winner(new)] is not donor:
            raise ValueError("the exact transplanted capture winner must win")
        output[index] = dict(base[index], candidates=new)
    return dict(stock, source=dict(stock["source"], probes=output))
