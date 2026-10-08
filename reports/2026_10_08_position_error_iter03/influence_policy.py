"""Frozen diagnostic deletion rule, independent of reference error."""


def choose(document, threshold=2.0):
    rows = document["candidates"]
    control = {r["arm"]: r for r in rows if r["removed_satellite"] is None}
    eligible = [
        r
        for r in rows
        if r["arm"] == "fitted-c" and r["removed_satellite"] is not None and r["converged"]
    ]
    if not eligible:
        return control
    selected = max(eligible, key=lambda r: (r["displacement_km"], -r["removed_satellite"]))
    pair = {r["arm"]: r for r in rows if r["removed_satellite"] == selected["removed_satellite"]}
    if selected["displacement_km"] <= threshold or not all(r["converged"] for r in pair.values()):
        return control
    return pair
