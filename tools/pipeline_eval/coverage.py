"""Horizontal error reached by a specified fraction of all offered recordings."""

from bisect import bisect_right
from collections import Counter, defaultdict

from .scoring import _reference, score

PERCENTILES = (50, 75, 90, 95)


def at_coverage(errors):
    ordered = sorted(x for x in errors if x is not None)
    by_percent = {}
    for p in PERCENTILES:
        # Inverse of the empirical all-offer CDF. A withholding has no finite error radius.
        needed = (p * len(errors) + 99) // 100
        by_percent[str(p)] = ordered[needed - 1] if 0 < needed <= len(ordered) else None
    return dict(offered=len(errors), published=len(ordered), km_at_percent=by_percent)


def comparison(pairs):
    candidates = sorted(a for a, _ in pairs if a is not None)
    originals = sorted(b for _, b in pairs if b is not None)
    shared = [(a, b) for a, b in pairs if a is not None and b is not None]
    margins = {}
    for p in (5, 10):
        factor = 1 + p / 100
        # Evaluate every reference jump, including its final jump and exact ties.
        gap = max(
            (
                bisect_right(originals, b) - bisect_right(candidates, b * factor)
                for b in set(originals)
            ),
            default=0,
        )
        margins[str(p)] = dict(
            shared_within_margin=sum(a <= factor * b for a, b in shared),
            largest_cdf_shortfall_recordings=max(0, gap),
        )
    return dict(
        baseline_scored=len(pairs),
        candidate=at_coverage([a for a, _ in pairs]),
        original=at_coverage([b for _, b in pairs]),
        shared_fixes=len(shared),
        gained_fixes=len(candidates) - len(shared),
        lost_fixes=len(originals) - len(shared),
        relative_error_margin_percent=margins,
    )


def evaluate(refs, predictions):
    refs = list(refs)
    _, rows = score(refs, predictions)
    reference_by_id = {ref["id"]: ref for ref in refs}
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"], row["condition"], row["arm"]].append(row)
    result = []
    for (group, condition, arm), subset in sorted(groups.items()):
        entry = dict(
            group=group,
            condition=condition,
            arm=arm,
            offered=len(subset),
            statuses=dict(Counter(r["status"] for r in subset)),
        )
        known = [r for r in subset if r["v5_scored"]]
        if condition == "present":
            entry["candidate"] = at_coverage([r["error_km"] for r in subset])
            if known:
                entry["matched"] = comparison([(r["error_km"], r["v5_error_km"]) for r in known])
        elif condition == "missing":
            # An actual publication on a wrong offer is still false at any horizontal error.
            outcomes = (predictions.get(r["id"], {}).get("result", {}) for r in subset)
            entry["false_publications"] = sum(
                outcome.get("arms", {}).get(arm, {}).get("latlon") is not None
                for outcome in outcomes
            )
            entry["v5_scored"] = len(known)
            if known:
                original = (_reference(reference_by_id[r["id"]], "baseline", arm) for r in known)
                entry["v5_false_publications"] = sum(
                    a.get("latlon") is not None or a.get("error_km") is not None for a in original
                )
        else:
            raise ValueError(f"unrecognized offered-region condition {condition!r}")
        result.append(entry)
    return result
