"""Independent distance validation for the shared detection-effect replay."""
import math
import statistics

import score_consistent_replay as previous

VARIANTS = ("old", "mixture", "shared")


def validate_branch(saved, result):
    rows = result.get("point_components", [])
    if not rows or set(result.get("selected", {})) != set(VARIANTS):
        raise ValueError("missing points or selected variants")
    for row in rows:
        scores = row.get("variant_scores", {})
        if set(scores) != set(VARIANTS):
            raise ValueError("unexpected variant inventory")
        if any(set(scores[v]) != set(scores["old"]) for v in VARIANTS):
            raise ValueError("score arms differ")
    checks = {}
    for variant in ("mixture", "shared"):
        def project(row):
            return {**row, "variant_scores": {
                "old": row["variant_scores"]["old"],
                "consistent": row["variant_scores"][variant]}}
        projected = [project(row) for row in rows]
        parity = previous.replay.parity_report(saved, projected)
        previous.validate_branch(saved, {
            "grid_count": result.get("grid_count"),
            "point_components": projected, "parity": parity,
            "selected": {"old": project(result["selected"]["old"]),
                         "consistent": project(result["selected"][variant])}})
        checks[variant] = parity
    selected = {v: previous.replay.select_min(rows, v, "D_plus_geometry") for v in VARIANTS}
    selected["D"] = previous.replay.select_min(rows, "old", "D")
    return {"selected": selected, "parity": checks}


def distance_row(sid, prior, saved, validated, reference):
    if (not sid or prior not in {"sacramento", "reno"} or len(reference) != 2 or
            not all(math.isfinite(float(x)) for x in reference)):
        raise ValueError("invalid row identity/reference")
    selected = validated["selected"]
    return {
        "session_id": sid, "prior": prior,
        "errors_km": {v: previous.distance_km((p["latitude_deg"], p["longitude_deg"]), reference)
                      for v, p in selected.items()},
        "coordinates": {v: [p["latitude_deg"], p["longitude_deg"]] for v, p in selected.items()},
        "boundary_flags": {v: previous.boundary_flags(p, saved) for v, p in selected.items()},
    }


def summarize(rows, sessions):
    if len(sessions) != 4 or len(set(sessions)) != 4 or not all(sessions):
        raise ValueError("expected four sessions")
    expected = {(sid, prior) for sid in sessions for prior in ("sacramento", "reno")}
    keys = [(r.get("session_id"), r.get("prior")) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("incomplete/duplicate cohort")
    for r in rows:
        errors = r.get("errors_km", {})
        if set(errors) != {"D", *VARIANTS} or not all(
                math.isfinite(float(x)) and x >= 0 for x in errors.values()):
            raise ValueError("invalid error values")
    result = {}
    for prior in ("sacramento", "reno", "combined"):
        group = rows if prior == "combined" else [r for r in rows if r["prior"] == prior]
        comparisons = {}
        for baseline in ("D", "old", "mixture"):
            deltas = [r["errors_km"]["shared"] - r["errors_km"][baseline] for r in group]
            comparisons[baseline] = {"improved": sum(x < -1e-9 for x in deltas),
                                     "worsened": sum(x > 1e-9 for x in deltas),
                                     "tied": sum(abs(x) <= 1e-9 for x in deltas)}
        result[prior] = {"cases": len(group),
            "mean_error_km": {v: statistics.mean(r["errors_km"][v] for r in group) for v in ("D", *VARIANTS)},
            "median_error_km": {v: statistics.median(r["errors_km"][v] for r in group) for v in ("D", *VARIANTS)},
            "shared_vs": comparisons}
    return result
