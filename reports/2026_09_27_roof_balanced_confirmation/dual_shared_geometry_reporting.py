"""Reuse independently tested fixed-grid checks with explicit dual-effect labels."""
import shared_geometry_reporting as previous

TO_PREVIOUS = {"old": "old", "detection": "mixture", "dual": "shared", "D": "D"}
FROM_PREVIOUS = {v: k for k, v in TO_PREVIOUS.items()}
VARIANTS = ("old", "detection", "dual")


def renamed(mapping, names):
    return {names[k]: value for k, value in mapping.items()}


def validate_branch(saved, result):
    if set(result.get("selected", {})) != set(VARIANTS):
        raise ValueError("invalid dual variant inventory")
    def point(row):
        if set(row.get("variant_scores", {})) != set(VARIANTS):
            raise ValueError("invalid dual point variants")
        return {**row, "variant_scores": renamed(row["variant_scores"], TO_PREVIOUS)}
    projected = {**result,
                 "point_components": [point(row) for row in result["point_components"]],
                 "selected": {TO_PREVIOUS[name]: point(row) for name, row in result["selected"].items()}}
    checked = previous.validate_branch(saved, projected)
    selected = {FROM_PREVIOUS[name]: {**row, "variant_scores": renamed(row["variant_scores"], FROM_PREVIOUS)}
                for name, row in checked["selected"].items()}
    return {"selected": selected, "parity": renamed(checked["parity"], FROM_PREVIOUS)}


distance_row = previous.distance_row


def summarize(rows, sessions):
    projected = []
    for row in rows:
        if set(row.get("errors_km", {})) != {"D", *VARIANTS}:
            raise ValueError("invalid dual distance variants")
        projected.append({**row, "errors_km": renamed(row["errors_km"], TO_PREVIOUS)})
    result = previous.summarize(projected, sessions)
    return {prior: {"cases": values["cases"],
                    "mean_error_km": renamed(values["mean_error_km"], FROM_PREVIOUS),
                    "median_error_km": renamed(values["median_error_km"], FROM_PREVIOUS),
                    "dual_vs": renamed(values["shared_vs"], FROM_PREVIOUS)}
            for prior, values in result.items()}
