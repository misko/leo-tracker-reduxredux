"""Independent branch validation and distance summaries for three calibrations."""
from __future__ import annotations

import math
import statistics

import score_consistent_replay as previous

VARIANTS = ("old", "mean", "mixture")


def validate_branch(saved: dict, result: dict) -> dict:
    rows = result.get("point_components", [])
    if not rows or set(result.get("selected", {})) != set(VARIANTS):
        raise ValueError("missing mixture replay points or selections")
    for row in rows:
        scores = row.get("variant_scores", {})
        if set(scores) != set(VARIANTS):
            raise ValueError("missing or unexpected calibration variant")
        if any(set(scores[name]) != set(scores["old"]) for name in VARIANTS):
            raise ValueError("calibration variants have different score arms")

    # Reuse the frozen, independently tested coordinate/parity/minimum gates.
    # Each projection retains old plus exactly one candidate calibration.
    checks = {}
    for variant in ("mean", "mixture"):
        def project(row):
            return {**row, "variant_scores": {
                "old": row["variant_scores"]["old"],
                "consistent": row["variant_scores"][variant]}}
        projected = [project(row) for row in rows]
        parity = previous.replay.parity_report(saved, projected)
        branch = {
            "grid_count": result.get("grid_count"),
            "point_components": projected, "parity": parity,
            "selected": {"old": project(result["selected"]["old"]),
                         "consistent": project(result["selected"][variant])},
        }
        previous.validate_branch(saved, branch)
        checks[variant] = parity
    selected = {name: previous.replay.select_min(rows, name, "D_plus_geometry")
                for name in VARIANTS}
    selected["D"] = previous.replay.select_min(rows, "old", "D")
    return {"selected": selected, "parity": checks, "grid_count": len(rows)}


def distance_row(session_id: str, prior: str, saved: dict, validated: dict,
                 reference: tuple[float, float]) -> dict:
    if (not session_id or prior not in {"sacramento", "reno"} or
            len(reference) != 2 or
            not all(math.isfinite(float(value)) for value in reference)):
        raise ValueError("invalid distance-row identity or reference")
    selected = validated["selected"]
    errors = {name: previous.distance_km(
        (point["latitude_deg"], point["longitude_deg"]), reference)
        for name, point in selected.items()}
    return {
        "session_id": session_id, "prior": prior, "errors_km": errors,
        "mixture_minus_mean_km": errors["mixture"] - errors["mean"],
        "mixture_minus_D_km": errors["mixture"] - errors["D"],
        "mixture_minus_old_km": errors["mixture"] - errors["old"],
        "coordinates": {name: [point["latitude_deg"], point["longitude_deg"]]
                        for name, point in selected.items()},
        "boundary_flags": {name: previous.boundary_flags(point, saved)
                           for name, point in selected.items()},
        "parity": validated["parity"],
    }


def summarize(rows: list[dict], expected_sessions: list[str]) -> dict:
    if (len(expected_sessions) != 4 or len(set(expected_sessions)) != 4 or
            any(not session for session in expected_sessions)):
        raise ValueError("expected exactly four distinct frozen sessions")
    keys = [(row.get("session_id"), row.get("prior")) for row in rows]
    expected = {(session, prior) for session in expected_sessions
                for prior in ("sacramento", "reno")}
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("distance rows do not cover the complete cohort and priors once")
    for row in rows:
        errors = row.get("errors_km", {})
        if set(errors) != {"D", *VARIANTS} or not all(
                math.isfinite(float(value)) and float(value) >= 0
                for value in errors.values()):
            raise ValueError("distance error is missing, negative, or nonfinite")
    result = {}
    for prior in ("sacramento", "reno", "combined"):
        group = rows if prior == "combined" else [row for row in rows if row["prior"] == prior]
        if not group:
            raise ValueError("missing prior for distance summary")
        comparisons = {}
        for baseline in ("D", "old", "mean"):
            changes = [row["errors_km"]["mixture"] - row["errors_km"][baseline]
                       for row in group]
            comparisons[baseline] = {
                "improved": sum(value < -1e-9 for value in changes),
                "worsened": sum(value > 1e-9 for value in changes),
                "tied": sum(abs(value) <= 1e-9 for value in changes),
            }
        result[prior] = {
            "cases": len(group),
            "mean_error_km": {name: statistics.mean(row["errors_km"][name] for row in group)
                              for name in ("D", *VARIANTS)},
            "median_error_km": {name: statistics.median(row["errors_km"][name] for row in group)
                                for name in ("D", *VARIANTS)},
            "mixture_vs": comparisons,
        }
    return result
