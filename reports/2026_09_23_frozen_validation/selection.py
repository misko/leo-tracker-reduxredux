"""Frozen model-selection rule, independent of numerical fitting."""

import math

CONFIGURATIONS = [("baseline", 0.0)] + [
    (model, scale) for model in ("global", "scan") for scale in (0.2, 1.0, 5.0)
]


def select(rows, group_sizes):
    summaries = []
    for model, scale in CONFIGURATIONS:
        arms = [r for r in rows if (r["model"], r["scale_s"]) == (model, scale)]
        expected = {
            (group, count, prior)
            for group, size in group_sizes.items()
            for count in (1, 6, 16, size)
            for prior in ("sacramento", "reno")
        }
        keys = [(r["group"], r["view_scan_count"], r["prior"]) for r in arms]
        valid = len(keys) == len(expected) and set(keys) == expected
        valid = valid and all(
            not r.get("failure")
            and math.isfinite(r.get("reference_error_km", math.nan))
            and r.get("within_prior", False)
            and r.get("visibility_failure_count", 0) == 0
            and r.get("tau_boundary_count", 0) == 0
            and (model == "baseline" or r.get("stopping_rule_satisfied", False))
            for r in arms
        )
        summary = {"model": model, "scale_s": scale, "eligible": valid}
        if valid:
            lookup = {
                (r["group"], r["view_scan_count"], r["prior"]): r["reference_error_km"]
                for r in arms
            }
            losses = []
            for group, size in group_sizes.items():
                means = {
                    count: sum(lookup[group, count, p] for p in ("sacramento", "reno")) / 2
                    for count in (1, 6, 16, size)
                }
                losses.append((means[1] + (means[6] + means[16]) / 2 + means[size]) / 3)
            summary["mean_regime_error_km"] = sum(losses) / len(losses)
            summary["worst_error_km"] = max(lookup.values())
        summaries.append(summary)
    eligible = [s for s in summaries if s["eligible"]]
    if not eligible:
        return {"selected": None, "configurations": summaries}
    best = min(s["mean_regime_error_km"] for s in eligible)
    tied = [s for s in eligible if s["mean_regime_error_km"] <= best + 0.010]
    chosen = min(tied, key=lambda s: CONFIGURATIONS.index((s["model"], s["scale_s"])))
    return {"selected": chosen, "configurations": summaries, "tie_tolerance_km": 0.010}
